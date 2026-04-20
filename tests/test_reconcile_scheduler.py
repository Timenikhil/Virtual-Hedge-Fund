import sqlite3
import threading
import types
import unittest
from unittest.mock import patch

from vhf.models.allocation import AllocationMethod
from vhf.models.reconcile import ReconcileJob, ReconcileRunResult
from vhf.services.reconcile_scheduler import ReconcileScheduler


def _make_in_memory_connection():
    """Return a fake connection module backed by an in-memory SQLite DB."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute(
        """
        CREATE TABLE reconcile_jobs (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            PID INTEGER NOT NULL,
            INTERVAL_SECONDS INTEGER NOT NULL,
            METHOD TEXT NOT NULL,
            THRESHOLD REAL NOT NULL,
            APPLY INTEGER NOT NULL,
            EXECUTE_TRADES INTEGER NOT NULL,
            DRY_RUN_TRADES INTEGER NOT NULL,
            REVIEW_DATE TEXT,
            ENABLED INTEGER NOT NULL,
            AI_PROVIDER_MODE TEXT,
            AI_STRICT INTEGER NOT NULL DEFAULT 0,
            AI_TIMEOUT_SECONDS REAL NOT NULL DEFAULT 30.0,
            AI_CONTEXT TEXT,
            CREATED_AT TEXT NOT NULL,
            UPDATED_AT TEXT NOT NULL,
            LAST_RUN_AT TEXT,
            NEXT_RUN_AT TEXT,
            LAST_STATUS TEXT,
            LAST_ERROR TEXT,
            LOCKED_AT TEXT,
            LOCKED_BY TEXT,
            CONSECUTIVE_ERRORS INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.commit()

    conn = types.SimpleNamespace(
        client=db,
        db_lock=threading.RLock(),
        connect=lambda: None,
    )
    return conn


class ReconcileSchedulerTest(unittest.IsolatedAsyncioTestCase):
    @patch("vhf.services.reconcile_scheduler.run_reconcile_job")
    @patch("vhf.services.reconcile_scheduler.claim_due_reconcile_jobs")
    async def test_run_due_jobs_once_executes_each_claimed_job(self, mock_claim_due, mock_run_job):
        mock_claim_due.return_value = [
            ReconcileJob(
                job_id=1,
                portfolio_id=10,
                interval_seconds=86400,
                method=AllocationMethod.manual,
                threshold=0.02,
                apply=True,
                execute_trades=False,
                dry_run_trades=True,
                review_date="latest",
                enabled=True,
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            ),
            ReconcileJob(
                job_id=2,
                portfolio_id=11,
                interval_seconds=86400,
                method=AllocationMethod.manual,
                threshold=0.02,
                apply=True,
                execute_trades=False,
                dry_run_trades=True,
                review_date="latest",
                enabled=True,
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            ),
        ]
        mock_run_job.side_effect = [
            ReconcileRunResult(
                job_id=1,
                portfolio_id=10,
                status="applied",
                plan_status="applied",
                rebalance_required=True,
                applied=True,
                trades_executed=False,
                generated_at="2026-01-01T00:00:00+00:00",
            ),
            ReconcileRunResult(
                job_id=2,
                portfolio_id=11,
                status="noop",
                plan_status="noop",
                rebalance_required=False,
                applied=False,
                trades_executed=False,
                generated_at="2026-01-01T00:00:00+00:00",
            ),
        ]

        scheduler = ReconcileScheduler(poll_interval_seconds=86400, worker_id="test-worker")
        results = await scheduler.run_due_jobs_once()

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_run_job.call_count, 2)
        mock_claim_due.assert_called_once_with(worker_id="test-worker")


class ClaimDueReconcileJobsAtMostOnceTest(unittest.TestCase):
    """Verify that concurrent callers claim each job at most once."""

    _NOW = "2026-01-01T12:00:00+00:00"
    _PAST = "2026-01-01T11:00:00+00:00"  # before _NOW → job is due

    def _insert_due_job(self, db: sqlite3.Connection) -> None:
        db.execute(
            """
            INSERT INTO reconcile_jobs
                (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                 EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED,
                 CREATED_AT, UPDATED_AT, NEXT_RUN_AT)
            VALUES (1, 86400, 'manual', 0.02, 1, 0, 1, 1, ?, ?, ?)
            """,
            (self._NOW, self._NOW, self._PAST),
        )
        db.commit()

    def test_single_job_claimed_at_most_once_by_two_concurrent_workers(self):
        from vhf.db.operations import claim_due_reconcile_jobs

        conn = _make_in_memory_connection()
        self._insert_due_job(conn.client)

        results: list[list] = [[], []]
        barrier = threading.Barrier(2)

        def worker(idx: int, wid: str) -> None:
            barrier.wait()
            results[idx] = claim_due_reconcile_jobs(worker_id=wid, now_iso=self._NOW)

        with patch("vhf.db.operations.connection", conn):
            t1 = threading.Thread(target=worker, args=(0, "worker-A"))
            t2 = threading.Thread(target=worker, args=(1, "worker-B"))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        all_claimed = results[0] + results[1]
        claimed_ids = [j.job_id for j in all_claimed]
        # Job must be claimed at most once across both workers.
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)))
        # And the single due job must have been claimed by exactly one worker.
        self.assertEqual(len(all_claimed), 1)

    def test_two_jobs_each_claimed_exactly_once_across_two_workers(self):
        from vhf.db.operations import claim_due_reconcile_jobs

        conn = _make_in_memory_connection()
        self._insert_due_job(conn.client)
        self._insert_due_job(conn.client)

        results: list[list] = [[], []]
        barrier = threading.Barrier(2)

        def worker(idx: int, wid: str) -> None:
            barrier.wait()
            results[idx] = claim_due_reconcile_jobs(worker_id=wid, now_iso=self._NOW)

        with patch("vhf.db.operations.connection", conn):
            t1 = threading.Thread(target=worker, args=(0, "worker-A"))
            t2 = threading.Thread(target=worker, args=(1, "worker-B"))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        all_claimed = results[0] + results[1]
        claimed_ids = [j.job_id for j in all_claimed]
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)), "duplicate claims detected")
        self.assertEqual(len(all_claimed), 2, "both jobs must be claimed exactly once")

    def test_already_locked_job_not_reclaimed_before_timeout(self):
        from vhf.db.operations import claim_due_reconcile_jobs

        conn = _make_in_memory_connection()
        # Insert a job locked 10 seconds ago — well within the 3600s timeout.
        locked_at = "2026-01-01T11:59:50+00:00"
        conn.client.execute(
            """
            INSERT INTO reconcile_jobs
                (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                 EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED,
                 CREATED_AT, UPDATED_AT, NEXT_RUN_AT, LOCKED_AT, LOCKED_BY)
            VALUES (1, 86400, 'manual', 0.02, 1, 0, 1, 1, ?, ?, ?, ?, 'other-worker')
            """,
            (self._NOW, self._NOW, self._PAST, locked_at),
        )
        conn.client.commit()

        with patch("vhf.db.operations.connection", conn):
            claimed = claim_due_reconcile_jobs(worker_id="worker-A", now_iso=self._NOW)

        self.assertEqual(claimed, [], "job locked within timeout must not be reclaimed")


    def test_stale_lock_reclaimed_after_timeout(self):
        from vhf.db.operations import claim_due_reconcile_jobs

        conn = _make_in_memory_connection()
        # Insert a job locked 3601 seconds before _NOW → stale.
        stale_locked_at = "2026-01-01T11:00:00+00:00"  # exactly 3600s before _NOW
        # Use a slightly earlier timestamp to be safely past the threshold.
        stale_locked_at = "2026-01-01T10:59:59+00:00"
        conn.client.execute(
            """
            INSERT INTO reconcile_jobs
                (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                 EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED,
                 CREATED_AT, UPDATED_AT, NEXT_RUN_AT, LOCKED_AT, LOCKED_BY)
            VALUES (1, 86400, 'manual', 0.02, 1, 0, 1, 1, ?, ?, ?, ?, 'crashed-worker')
            """,
            (self._NOW, self._NOW, self._PAST, stale_locked_at),
        )
        conn.client.commit()

        with patch("vhf.db.operations.connection", conn):
            claimed = claim_due_reconcile_jobs(worker_id="worker-A", now_iso=self._NOW)

        self.assertEqual(len(claimed), 1, "stale-locked job must be reclaimable")
        self.assertEqual(claimed[0].locked_by, "worker-A")


if __name__ == "__main__":
    unittest.main()
