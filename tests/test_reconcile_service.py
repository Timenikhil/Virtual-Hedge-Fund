import unittest
from unittest.mock import patch

from vhf.models.allocation import AIProviderMode, AllocationMethod
from vhf.models.rebalance import RebalanceLeg, RebalancePlan
from vhf.models.reconcile import ReconcileJob
from vhf.services.reconcile_service import ReconcileServiceError, run_reconcile_job


class ReconcileServiceTest(unittest.TestCase):
    @patch("vhf.services.reconcile_service.get_reconcile_job")
    def test_disabled_job_raises(self, mock_get_job):
        mock_get_job.return_value = ReconcileJob(
            job_id=1,
            portfolio_id=10,
            interval_seconds=86400,
            method=AllocationMethod.manual,
            threshold=0.02,
            apply=True,
            execute_trades=False,
            dry_run_trades=True,
            review_date="latest",
            enabled=False,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

        with self.assertRaises(ReconcileServiceError):
            run_reconcile_job(1)

    @patch("vhf.services.reconcile_service.update_reconcile_job_after_run")
    @patch("vhf.services.reconcile_service.build_rebalance_plan")
    @patch("vhf.services.reconcile_service.get_reconcile_job")
    def test_reconcile_run_records_success(
        self,
        mock_get_job,
        mock_build_plan,
        mock_update,
    ):
        mock_get_job.return_value = ReconcileJob(
            job_id=2,
            portfolio_id=11,
            interval_seconds=86400,
            method=AllocationMethod.manual,
            threshold=0.02,
            apply=True,
            execute_trades=False,
            dry_run_trades=True,
            review_date="latest",
            ai_provider_mode=AIProviderMode.remote,
            ai_strict=True,
            ai_timeout_seconds=15.0,
            ai_context={"source": "job"},
            enabled=True,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        mock_build_plan.return_value = RebalancePlan(
            portfolio_id=11,
            account="ACCT1",
            method=AllocationMethod.manual,
            threshold=0.02,
            strategies=["s1", "s2"],
            current_weights=[0.5, 0.5],
            target_weights=[0.6, 0.4],
            legs=[
                RebalanceLeg(
                    strategy_id="s1",
                    current_weight=0.5,
                    target_weight=0.6,
                    delta_weight=0.1,
                    trade_weight=0.1,
                    action="buy",
                ),
                RebalanceLeg(
                    strategy_id="s2",
                    current_weight=0.5,
                    target_weight=0.4,
                    delta_weight=-0.1,
                    trade_weight=-0.1,
                    action="sell",
                ),
            ],
            l1_drift=0.2,
            max_abs_drift=0.1,
            rebalance_required=True,
            applied=True,
            generated_at="2026-01-01T00:00:00+00:00",
        )

        result = run_reconcile_job(2)

        self.assertEqual(result.job_id, 2)
        self.assertTrue(result.applied)
        self.assertEqual(result.status, "applied")
        mock_update.assert_called_once()

        rebalance_request = mock_build_plan.call_args.args[0]
        self.assertEqual(rebalance_request.ai_provider_mode, AIProviderMode.remote)
        self.assertTrue(rebalance_request.ai_strict)
        self.assertEqual(rebalance_request.ai_timeout_seconds, 15.0)
        self.assertEqual(rebalance_request.ai_context, {"source": "job"})

    @patch("vhf.services.reconcile_service.update_reconcile_job_after_run")
    @patch("vhf.services.reconcile_service.generate_orders_csv")
    @patch("vhf.services.reconcile_service.build_rebalance_plan")
    @patch("vhf.services.reconcile_service.get_reconcile_job")
    def test_execute_trades_uses_non_hold_legs_only(
        self,
        mock_get_job,
        mock_build_plan,
        mock_generate_orders,
        mock_update,
    ):
        mock_get_job.return_value = ReconcileJob(
            job_id=3,
            portfolio_id=12,
            interval_seconds=86400,
            method=AllocationMethod.manual,
            threshold=0.02,
            apply=True,
            execute_trades=True,
            dry_run_trades=True,
            review_date="latest",
            enabled=True,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        mock_build_plan.return_value = RebalancePlan(
            portfolio_id=12,
            account="ACCT1",
            method=AllocationMethod.manual,
            threshold=0.02,
            strategies=["s1", "s2", "s3"],
            current_weights=[0.2, 0.4, 0.4],
            target_weights=[0.4, 0.2, 0.4],
            legs=[
                RebalanceLeg(
                    strategy_id="s1",
                    current_weight=0.2,
                    target_weight=0.4,
                    delta_weight=0.2,
                    trade_weight=0.2,
                    action="buy",
                ),
                RebalanceLeg(
                    strategy_id="s2",
                    current_weight=0.4,
                    target_weight=0.2,
                    delta_weight=-0.2,
                    trade_weight=-0.2,
                    action="sell",
                ),
                RebalanceLeg(
                    strategy_id="s3",
                    current_weight=0.4,
                    target_weight=0.4,
                    delta_weight=0.0,
                    trade_weight=0.0,
                    action="hold",
                ),
            ],
            l1_drift=0.4,
            max_abs_drift=0.2,
            rebalance_required=True,
            applied=True,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        mock_generate_orders.return_value = "header\n1\n"

        result = run_reconcile_job(3)

        self.assertTrue(result.trades_executed)
        self.assertEqual(mock_generate_orders.call_count, 2)
        called_strategies = {call.kwargs["strategy"] for call in mock_generate_orders.call_args_list}
        self.assertEqual(called_strategies, {"s1", "s2"})
        mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
