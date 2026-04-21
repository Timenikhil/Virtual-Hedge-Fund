"""Stress tests: concurrent load + degraded-provider conditions.

Two risk surfaces no unit test exercises today:
  1. `allocate_portfolio()` under many simultaneous callers (retry-layer contention).
  2. `claim_due_reconcile_jobs()` at 10-worker × 50-job scale (atomic claim race).
"""

from __future__ import annotations

import random
import sqlite3
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from tests.test_reconcile_scheduler import _make_in_memory_connection
from vhf.ai.weight_allocator_provider import WeightAllocatorProviderError
from vhf.models.allocation import (
    AIProviderMode,
    AllocationMethod,
    AllocationRequest,
)
from vhf.models.portfolio import Portfolio
from vhf.models.strategy import StrategyPrice
from vhf.services.allocation_service import allocate_portfolio


# ---------- Provider doubles ---------------------------------------------


class _ConstProvider:
    name = "const"

    def __init__(self, weights):
        self.weights = weights
        self._lock = threading.Lock()
        self.calls = 0

    def allocate(self, context, *, timeout_seconds):
        with self._lock:
            self.calls += 1
        return list(self.weights)


class _FlakyProvider:
    """Thread-safe coin-flip failure model."""

    name = "flaky"

    def __init__(self, fail_probability, weights, seed=None):
        self.p = fail_probability
        self.weights = weights
        self._rng = random.Random(seed)
        self._rng_lock = threading.Lock()
        self._call_lock = threading.Lock()
        self.calls = 0

    def allocate(self, context, *, timeout_seconds):
        with self._rng_lock:
            should_fail = self._rng.random() < self.p
        with self._call_lock:
            self.calls += 1
        if should_fail:
            raise WeightAllocatorProviderError("flaky failure")
        return list(self.weights)


class _DeadProvider:
    name = "dead"

    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0

    def allocate(self, context, *, timeout_seconds):
        with self._lock:
            self.calls += 1
        raise WeightAllocatorProviderError("provider unavailable")


class _TokenEchoProvider:
    """Fails once per token, then succeeds — used to probe per-thread retry-context isolation."""

    name = "token-echo"

    def __init__(self, weights):
        self.weights = weights
        self._lock = threading.Lock()
        self._attempts: dict[str, int] = {}
        self.observations: list[tuple[str | None, dict | None]] = []

    def allocate(self, context, *, timeout_seconds):
        token = (context.get("request_context") or {}).get("token")
        retry = context.get("_retry")
        with self._lock:
            self.observations.append((token, dict(retry) if retry else None))
            n = self._attempts.get(token, 0)
            self._attempts[token] = n + 1
        if n == 0:
            raise WeightAllocatorProviderError(f"first-call failure for {token}")
        return list(self.weights)


# ---------- Shared fixtures ----------------------------------------------

_STRATEGIES = ["A", "B", "C"]


def _portfolio_fixture() -> Portfolio:
    return Portfolio(
        portfolio_id=1,
        portfolio_name="p1",
        strategies=list(_STRATEGIES),
        weights=[0.4, 0.3, 0.3],
        live=False,
    )


def _strategy_price_fixture(strategy_id: str) -> StrategyPrice:
    return StrategyPrice(
        strategy_id=strategy_id,
        name=strategy_id,
        description="",
        category="eq",
        prices=[1.0, 1.05, 1.1, 1.15, 1.2],
    )


# ---------- Class 1: allocate_portfolio() under concurrent load ----------


class ConcurrentAllocationStressTest(unittest.TestCase):
    def setUp(self):
        self._patches = [
            patch("vhf.services.allocation_service.record_allocation_snapshot"),
            patch("vhf.services.allocation_service.update_portfolio_weights"),
            patch(
                "vhf.services.allocation_service.get_db_strat",
                side_effect=_strategy_price_fixture,
            ),
            patch(
                "vhf.services.allocation_service.get_db_portfolio_id",
                return_value=_portfolio_fixture(),
            ),
            patch("vhf.services.allocation_service.resolve_allocator_provider"),
        ]
        mocks = [p.start() for p in self._patches]
        self.addCleanup(self._stop_patches)
        # `resolve_allocator_provider` is the last patch in the list.
        self._mock_resolve = mocks[-1]

    def _stop_patches(self):
        for p in self._patches:
            p.stop()

    def _run_concurrent(
        self,
        n: int,
        provider,
        *,
        ai_max_retries: int = 1,
        ai_strict: bool = False,
        ai_context_builder=None,
    ):
        self._mock_resolve.return_value = (AIProviderMode.local, provider)
        barrier = threading.Barrier(n)
        errors: list[BaseException] = []
        results: list = [None] * n
        errors_lock = threading.Lock()

        def worker(idx: int):
            try:
                barrier.wait(timeout=5)
                req = AllocationRequest(
                    portfolio_id=1,
                    method=AllocationMethod.ai_weighted,
                    ai_provider_mode=AIProviderMode.local,
                    ai_max_retries=ai_max_retries,
                    ai_strict=ai_strict,
                    ai_context=ai_context_builder(idx) if ai_context_builder else None,
                )
                results[idx] = allocate_portfolio(req)
            except BaseException as exc:  # noqa: BLE001 — collect all escapees
                with errors_lock:
                    errors.append(exc)

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(worker, range(n)))

        return results, errors

    def test_N_concurrent_happy_path_no_fallback(self):
        provider = _ConstProvider([0.5, 0.3, 0.2])
        results, errors = self._run_concurrent(20, provider)

        self.assertEqual(errors, [], f"unexpected exceptions: {errors!r}")
        for r in results:
            self.assertIsNotNone(r)
            self.assertFalse(r.fallback_applied)
            self.assertEqual(r.ai_retry_count, 0)
            self.assertAlmostEqual(sum(r.target_weights), 1.0, places=6)
            self.assertAlmostEqual(r.target_weights[0], 0.5, places=6)
            self.assertAlmostEqual(r.target_weights[1], 0.3, places=6)
            self.assertAlmostEqual(r.target_weights[2], 0.2, places=6)
        self.assertEqual(provider.calls, 20)

    def test_N_concurrent_flaky_provider_each_caller_resolves(self):
        provider = _FlakyProvider(fail_probability=0.5, weights=[0.5, 0.3, 0.2], seed=42)
        results, errors = self._run_concurrent(20, provider, ai_max_retries=2)

        self.assertEqual(errors, [], f"unexpected exceptions: {errors!r}")
        for r in results:
            self.assertIsNotNone(r)
            self.assertAlmostEqual(sum(r.target_weights), 1.0, places=6)
            if r.fallback_applied:
                for w in r.target_weights:
                    self.assertAlmostEqual(w, 1 / 3, places=6)
            else:
                self.assertAlmostEqual(r.target_weights[0], 0.5, places=6)
                self.assertAlmostEqual(r.target_weights[1], 0.3, places=6)
                self.assertAlmostEqual(r.target_weights[2], 0.2, places=6)

    def test_N_concurrent_dead_provider_all_fallback(self):
        provider = _DeadProvider()
        results, errors = self._run_concurrent(20, provider, ai_max_retries=1)

        self.assertEqual(errors, [], f"unexpected exceptions: {errors!r}")
        for r in results:
            self.assertTrue(r.fallback_applied)
            self.assertEqual(r.ai_retry_count, 1)
            for w in r.target_weights:
                self.assertAlmostEqual(w, 1 / 3, places=6)
        # 20 threads × (1 initial + 1 retry) = 40 calls
        self.assertEqual(provider.calls, 40)

    def test_retry_context_isolated_per_thread(self):
        provider = _TokenEchoProvider([0.5, 0.3, 0.2])
        tokens = [uuid.uuid4().hex for _ in range(10)]

        results, errors = self._run_concurrent(
            10,
            provider,
            ai_max_retries=1,
            ai_context_builder=lambda idx: {"token": tokens[idx]},
        )
        self.assertEqual(errors, [], f"unexpected exceptions: {errors!r}")
        for r in results:
            self.assertIsNotNone(r)
            self.assertFalse(r.fallback_applied)
            self.assertEqual(r.ai_retry_count, 1)

        initial_tokens = sorted(t for t, retry in provider.observations if retry is None)
        retry_tokens = sorted(t for t, retry in provider.observations if retry is not None)
        self.assertEqual(initial_tokens, sorted(tokens))
        self.assertEqual(retry_tokens, sorted(tokens))

        # Critical isolation assertion: every retry's parse_error must reference
        # its own token — cross-thread mutation would leave a foreign token here.
        for token, retry in provider.observations:
            if retry is None:
                continue
            self.assertIn("parse_error", retry)
            self.assertIn(f"first-call failure for {token}", retry["parse_error"])


# ---------- Class 2: claim_due_reconcile_jobs() under concurrent load ----


class ConcurrentJobClaimingStressTest(unittest.TestCase):
    _NOW = "2026-04-21T12:00:00+00:00"
    _PAST = "2026-04-21T11:00:00+00:00"
    _STALE_LOCKED_AT = "2026-04-21T10:59:00+00:00"  # > 3600s before NOW → stale

    @staticmethod
    def _insert_due(db: sqlite3.Connection, n: int, now: str, past: str) -> None:
        for _ in range(n):
            db.execute(
                """
                INSERT INTO reconcile_jobs
                    (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                     EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED,
                     CREATED_AT, UPDATED_AT, NEXT_RUN_AT)
                VALUES (1, 86400, 'manual', 0.02, 1, 0, 1, 1, ?, ?, ?)
                """,
                (now, now, past),
            )
        db.commit()

    @staticmethod
    def _insert_stale_locked(db: sqlite3.Connection, n: int, now: str, past: str, locked_at: str) -> None:
        for _ in range(n):
            db.execute(
                """
                INSERT INTO reconcile_jobs
                    (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                     EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED,
                     CREATED_AT, UPDATED_AT, NEXT_RUN_AT, LOCKED_AT, LOCKED_BY)
                VALUES (1, 86400, 'manual', 0.02, 1, 0, 1, 1, ?, ?, ?, ?, 'crashed-worker')
                """,
                (now, now, past, locked_at),
            )
        db.commit()

    @classmethod
    def _race_claim_workers(cls, num_workers: int, now_iso: str, per_call_limit: int):
        """Spin up `num_workers` barrier-synchronised workers that each make ONE claim call.

        Each worker claims up to `per_call_limit` jobs. Setting per_call_limit below the
        pending-job count forces distribution across workers instead of a winner-takes-all.
        A single call per worker matches the real scheduler-tick pattern and avoids the
        "same now_iso returns already-claimed batch" infinite loop.
        """
        from vhf.db.operations import claim_due_reconcile_jobs

        results: list[list] = [[] for _ in range(num_workers)]
        barrier = threading.Barrier(num_workers)

        def worker(idx: int):
            wid = f"w{idx}"
            barrier.wait(timeout=5)
            results[idx] = claim_due_reconcile_jobs(
                worker_id=wid, now_iso=now_iso, limit=per_call_limit
            )

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            list(pool.map(worker, range(num_workers)))

        return results

    def test_10_workers_50_jobs_no_duplicate_claims(self):
        conn = _make_in_memory_connection()
        self._insert_due(conn.client, 50, self._NOW, self._PAST)

        with patch("vhf.db.operations.connection", conn):
            per_worker = self._race_claim_workers(10, self._NOW, per_call_limit=5)

        all_claimed = [j for group in per_worker for j in group]
        claimed_ids = [j.job_id for j in all_claimed]
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)), "duplicate claims detected")
        self.assertEqual(len(claimed_ids), 50, "every job must be claimed exactly once")

    def test_5_workers_reclaim_10_stale_locked_jobs(self):
        conn = _make_in_memory_connection()
        self._insert_stale_locked(conn.client, 10, self._NOW, self._PAST, self._STALE_LOCKED_AT)

        with patch("vhf.db.operations.connection", conn):
            per_worker = self._race_claim_workers(5, self._NOW, per_call_limit=2)

        all_claimed = [j for group in per_worker for j in group]
        claimed_ids = [j.job_id for j in all_claimed]
        fresh_workers = {f"w{i}" for i in range(5)}
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)), "duplicate claims detected")
        self.assertEqual(len(claimed_ids), 10, "all 10 stale jobs must be reclaimed")
        for j in all_claimed:
            self.assertIn(j.locked_by, fresh_workers)

    def test_claim_release_reclaim_cycle_no_duplicates(self):
        from vhf.db.operations import update_reconcile_job_after_run

        conn = _make_in_memory_connection()
        self._insert_due(conn.client, 20, self._NOW, self._PAST)

        with patch("vhf.db.operations.connection", conn):
            # Round 1: claim everything (20 jobs / 4 workers = 5 each with limit=5)
            round1 = self._race_claim_workers(4, self._NOW, per_call_limit=5)
            r1_ids = [j.job_id for g in round1 for j in g]
            self.assertEqual(len(r1_ids), 20)
            self.assertEqual(len(r1_ids), len(set(r1_ids)))

            # Release each claimed job with a past NEXT_RUN_AT so it becomes due again.
            for job_id in r1_ids:
                update_reconcile_job_after_run(
                    job_id=job_id,
                    last_status="applied",
                    last_error=None,
                    next_run_at=self._PAST,
                    last_run_at=self._NOW,
                    success=True,
                )

            # Round 2: fresh workers must reclaim all 20, no duplicates.
            round2 = self._race_claim_workers(4, self._NOW, per_call_limit=5)
            r2_ids = [j.job_id for g in round2 for j in g]
            self.assertEqual(len(r2_ids), 20, "all 20 jobs must be re-claimed after release")
            self.assertEqual(len(r2_ids), len(set(r2_ids)), "no duplicates in round 2")


if __name__ == "__main__":
    unittest.main()
