from __future__ import annotations

import asyncio
import os
import socket

from vhf.db.operations import claim_due_reconcile_jobs
from vhf.logging.log import logger
from vhf.models.reconcile import ReconcileRunResult
from vhf.services.reconcile_service import ReconcileServiceError, run_reconcile_job

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR

DEFAULT_SCHEDULER_POLL_SECONDS = SECONDS_PER_DAY
MIN_SCHEDULER_POLL_SECONDS = 5

DEFAULT_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
SCHEDULER_WORKER_ID_ENV = "RECONCILE_SCHEDULER_WORKER_ID"


class ReconcileScheduler:
    """Background poller that claims and executes due reconcile jobs."""

    def __init__(
        self,
        poll_interval_seconds: int = DEFAULT_SCHEDULER_POLL_SECONDS,
        worker_id: str | None = None,
    ):
        self.poll_interval_seconds = max(int(poll_interval_seconds), MIN_SCHEDULER_POLL_SECONDS)
        self.worker_id = (worker_id or os.getenv(SCHEDULER_WORKER_ID_ENV, DEFAULT_WORKER_ID)).strip()
        if self.worker_id == "":
            self.worker_id = DEFAULT_WORKER_ID
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="reconcile-scheduler")
        logger.info(
            "Reconcile scheduler started (poll=%ss worker_id=%s)",
            self.poll_interval_seconds,
            self.worker_id,
        )

    async def stop(self) -> None:
        if not self.is_running:
            return
        self._stop_event.set()
        assert self._task is not None
        try:
            await self._task
        finally:
            self._task = None
            logger.info("Reconcile scheduler stopped")

    async def run_due_jobs_once(self) -> list[ReconcileRunResult]:
        due_jobs = await asyncio.to_thread(claim_due_reconcile_jobs, worker_id=self.worker_id)
        results: list[ReconcileRunResult] = []
        for job in due_jobs:
            try:
                result = await asyncio.to_thread(run_reconcile_job, job.job_id)
                results.append(result)
            except ReconcileServiceError as exc:
                logger.error("Reconcile job failed job_id=%s error=%s", job.job_id, exc)
            except Exception:
                logger.exception("Unexpected scheduler failure job_id=%s", job.job_id)
        return results

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.run_due_jobs_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue


SCHEDULER_ENABLED = os.getenv("RECONCILE_SCHEDULER_ENABLED", "true").lower() in {"1", "true", "yes"}
SCHEDULER_POLL_SECONDS = int(
    os.getenv("RECONCILE_SCHEDULER_POLL_SECONDS", str(DEFAULT_SCHEDULER_POLL_SECONDS))
)
scheduler = ReconcileScheduler(poll_interval_seconds=SCHEDULER_POLL_SECONDS)
