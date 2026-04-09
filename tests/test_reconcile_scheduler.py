import unittest
from unittest.mock import patch

from vhf.models.allocation import AllocationMethod
from vhf.models.reconcile import ReconcileJob, ReconcileRunResult
from vhf.services.reconcile_scheduler import ReconcileScheduler


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


if __name__ == "__main__":
    unittest.main()
