import unittest
from unittest.mock import patch

from vhf.models.allocation import AllocationMethod, AllocationResult
from vhf.models.portfolio import Portfolio
from vhf.models.rebalance import RebalanceRequest
from vhf.services.rebalance_engine import RebalanceEngineError, build_rebalance_plan


class RebalanceEngineTest(unittest.TestCase):
    @patch("vhf.services.rebalance_engine.record_rebalance_run")
    @patch("vhf.services.rebalance_engine.update_portfolio_weights")
    @patch("vhf.services.rebalance_engine.get_portfolio_account")
    @patch("vhf.services.rebalance_engine.allocate_portfolio")
    @patch("vhf.services.rebalance_engine.get_db_portfolio_id")
    def test_preview_plan_with_trade_legs(
        self,
        mock_get_portfolio,
        mock_allocate,
        mock_get_account,
        mock_update,
        mock_record,
    ):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=10,
            portfolio_name="p10",
            strategies=["s1", "s2"],
            weights=[0.8, 0.2],
            live=False,
        )
        mock_allocate.return_value = AllocationResult(
            portfolio_id=10,
            method=AllocationMethod.manual,
            strategies=["s1", "s2"],
            raw_weights=[0.5, 0.5],
            target_weights=[0.5, 0.5],
            generated_at="2026-01-01T00:00:00+00:00",
        )
        mock_get_account.return_value = "ACCT1"

        plan = build_rebalance_plan(
            RebalanceRequest(
                portfolio_id=10,
                threshold=0.1,
                apply=False,
            )
        )

        self.assertTrue(plan.rebalance_required)
        self.assertFalse(plan.applied)
        self.assertEqual(plan.legs[0].action, "sell")
        self.assertEqual(plan.legs[1].action, "buy")
        mock_update.assert_not_called()
        mock_record.assert_called_once()

    @patch("vhf.services.rebalance_engine.record_rebalance_run")
    @patch("vhf.services.rebalance_engine.update_portfolio_weights")
    @patch("vhf.services.rebalance_engine.get_portfolio_account")
    @patch("vhf.services.rebalance_engine.allocate_portfolio")
    @patch("vhf.services.rebalance_engine.get_db_portfolio_id")
    def test_apply_updates_weights_when_required(
        self,
        mock_get_portfolio,
        mock_allocate,
        mock_get_account,
        mock_update,
        mock_record,
    ):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=11,
            portfolio_name="p11",
            strategies=["s1", "s2"],
            weights=[0.9, 0.1],
            live=False,
        )
        mock_allocate.return_value = AllocationResult(
            portfolio_id=11,
            method=AllocationMethod.manual,
            strategies=["s1", "s2"],
            raw_weights=[0.2, 0.8],
            target_weights=[0.2, 0.8],
            generated_at="2026-01-01T00:00:00+00:00",
        )
        mock_get_account.return_value = "ACCT2"

        plan = build_rebalance_plan(
            RebalanceRequest(
                portfolio_id=11,
                threshold=0.05,
                apply=True,
            )
        )

        self.assertTrue(plan.applied)
        mock_update.assert_called_once_with(11, [0.2, 0.8])
        mock_record.assert_called_once()

    @patch("vhf.services.rebalance_engine.record_rebalance_run")
    @patch("vhf.services.rebalance_engine.update_portfolio_weights")
    @patch("vhf.services.rebalance_engine.get_portfolio_account")
    @patch("vhf.services.rebalance_engine.allocate_portfolio")
    @patch("vhf.services.rebalance_engine.get_db_portfolio_id")
    def test_no_rebalance_when_drift_below_threshold(
        self,
        mock_get_portfolio,
        mock_allocate,
        mock_get_account,
        mock_update,
        mock_record,
    ):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=12,
            portfolio_name="p12",
            strategies=["s1", "s2"],
            weights=[0.51, 0.49],
            live=False,
        )
        mock_allocate.return_value = AllocationResult(
            portfolio_id=12,
            method=AllocationMethod.manual,
            strategies=["s1", "s2"],
            raw_weights=[0.5, 0.5],
            target_weights=[0.5, 0.5],
            generated_at="2026-01-01T00:00:00+00:00",
        )
        mock_get_account.return_value = None

        plan = build_rebalance_plan(
            RebalanceRequest(
                portfolio_id=12,
                threshold=0.05,
                apply=True,
            )
        )

        self.assertFalse(plan.rebalance_required)
        self.assertFalse(plan.applied)
        self.assertTrue(all(leg.action == "hold" for leg in plan.legs))
        mock_update.assert_not_called()
        mock_record.assert_called_once()

    def test_negative_threshold_raises(self):
        with self.assertRaises(RebalanceEngineError):
            build_rebalance_plan(RebalanceRequest(portfolio_id=1, threshold=-0.01))


if __name__ == "__main__":
    unittest.main()
