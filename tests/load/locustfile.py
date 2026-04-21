"""Locust load-test scenarios for the VHF API.

Run against a uvicorn process that was started with DB_PATH pointed at a
seeded DB and AI_ALLOCATOR_MODE=local + AI_ALLOCATOR_LOCAL_MODULE=
tests.load.fake_allocator. See ``poe load-serve``.

Usage:
    locust -f tests/load/locustfile.py --host http://127.0.0.1:8001
    locust -f tests/load/locustfile.py --host http://127.0.0.1:8001 \\
        --headless --users 50 --spawn-rate 5 --run-time 2m --csv=tests/load/out/run

Portfolio IDs are discovered from ``GET /api/v1/portfolios`` on startup.
Override the candidate range with ``LOAD_PID_MIN`` / ``LOAD_PID_MAX``.
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, events, task


_portfolio_ids: list[int] = []


@events.test_start.add_listener
def _discover_portfolios(environment, **_kwargs):
    """Populate the PID pool before users start firing tasks."""
    global _portfolio_ids

    env_min = os.getenv("LOAD_PID_MIN")
    env_max = os.getenv("LOAD_PID_MAX")
    if env_min and env_max:
        _portfolio_ids = list(range(int(env_min), int(env_max) + 1))
        print(f"[locust] using PID range {env_min}..{env_max} ({len(_portfolio_ids)} PIDs)")
        return

    host = environment.host or "http://127.0.0.1:8001"
    try:
        import requests

        resp = requests.get(f"{host}/api/v1/portfolios", timeout=5.0)
        resp.raise_for_status()
        payload = resp.json()
        portfolios = payload.get("portfolios") if isinstance(payload, dict) else payload
        _portfolio_ids = [int(p["portfolio_id"]) for p in portfolios if "portfolio_id" in p]
    except Exception as exc:
        print(f"[locust] portfolio discovery failed: {exc}; falling back to [1..20]")
        _portfolio_ids = list(range(1, 21))

    if not _portfolio_ids:
        _portfolio_ids = list(range(1, 21))
    print(f"[locust] discovered {len(_portfolio_ids)} portfolios")


_ADMIN_API_KEY = os.getenv("LOAD_ADMIN_API_KEY", "").strip()


class VhfLoadUser(HttpUser):
    """Simulates a client hitting allocation + scheduler endpoints."""

    wait_time = between(0.1, 0.5)

    @task(4)
    def allocate_portfolio(self) -> None:
        if not _portfolio_ids:
            return
        pid = random.choice(_portfolio_ids)
        payload = {
            "portfolio_id": pid,
            "method": "ai_weighted",
            "ai_provider_mode": "local",
            "ai_strict": False,
            "ai_max_retries": 1,
            "ai_timeout_seconds": 5.0,
            "persist": False,
        }
        with self.client.post(
            "/api/v1/allocate-portfolio",
            json=payload,
            name="/allocate-portfolio",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @task(1)
    def run_due_reconcile_jobs(self) -> None:
        # Admin route — requires X-API-Key. Skip silently if not configured.
        if not _ADMIN_API_KEY:
            return
        with self.client.post(
            "/api/v1/admin/reconcile/scheduler/run-due",
            headers={"X-API-Key": _ADMIN_API_KEY},
            name="/admin/reconcile/scheduler/run-due",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
