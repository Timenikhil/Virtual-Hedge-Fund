import unittest
from unittest.mock import patch

from vhf.models.allocation import AIProviderMode, AllocationMethod, AllocationRequest
from vhf.models.portfolio import Portfolio
from vhf.models.strategy import StrategyPrice
from vhf.services.allocation_service import AllocationServiceError, allocate_portfolio


class FakeProvider:
    def __init__(self, *, response=None, error: Exception | None = None, name: str = "fake-provider"):
        self.response = response
        self.error = error
        self.name = name
        self.last_context = None
        self.last_timeout = None

    def allocate(self, context, *, timeout_seconds):
        self.last_context = context
        self.last_timeout = timeout_seconds
        if self.error is not None:
            raise self.error
        return self.response


class AllocationServiceTest(unittest.TestCase):
    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.update_portfolio_weights")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_manual_request_weights_are_normalized(
        self,
        mock_get_portfolio,
        mock_update_weights,
        mock_record,
    ):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=1,
            portfolio_name="p1",
            strategies=["s1", "s2"],
            weights=[0.9, 0.1],
            live=False,
        )

        result = allocate_portfolio(
            AllocationRequest(
                portfolio_id=1,
                method=AllocationMethod.manual,
                raw_weights=[2.0, 1.0],
                persist=True,
            )
        )

        self.assertEqual(result.method, AllocationMethod.manual)
        self.assertAlmostEqual(result.target_weights[0], 2.0 / 3.0)
        self.assertAlmostEqual(result.target_weights[1], 1.0 / 3.0)
        self.assertTrue(result.persisted)
        mock_update_weights.assert_called_once_with(1, result.target_weights)
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_manual_falls_back_to_equal_when_missing_weights(self, mock_get_portfolio, mock_record):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=2,
            portfolio_name="p2",
            strategies=["s1", "s2", "s3"],
            weights=None,
            live=False,
        )

        result = allocate_portfolio(AllocationRequest(portfolio_id=2, method=AllocationMethod.manual))

        self.assertTrue(result.fallback_applied)
        self.assertEqual(result.fallback_reason, "manual weights missing; used equal_weight fallback")
        self.assertEqual(result.target_weights, [1 / 3, 1 / 3, 1 / 3])
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.get_db_strat")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_score_weighted_uses_latest_prices(self, mock_get_portfolio, mock_get_strat, mock_record):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=3,
            portfolio_name="p3",
            strategies=["A", "B"],
            weights=None,
            live=False,
        )
        mock_get_strat.side_effect = [
            StrategyPrice(strategy_id="A", name="A", description="", category="", prices=[1, 2, 4]),
            StrategyPrice(strategy_id="B", name="B", description="", category="", prices=[1, 2, 1]),
        ]

        result = allocate_portfolio(AllocationRequest(portfolio_id=3, method=AllocationMethod.score_weighted))

        self.assertFalse(result.fallback_applied)
        self.assertAlmostEqual(result.target_weights[0], 0.8)
        self.assertAlmostEqual(result.target_weights[1], 0.2)
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_negative_weights_raise_error(self, mock_get_portfolio, mock_record):
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=4,
            portfolio_name="p4",
            strategies=["s1", "s2"],
            weights=[0.5, 0.5],
            live=False,
        )

        with self.assertRaises(AllocationServiceError):
            allocate_portfolio(
                AllocationRequest(
                    portfolio_id=4,
                    method=AllocationMethod.manual,
                    raw_weights=[0.9, -0.1],
                )
            )

        mock_record.assert_not_called()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.resolve_allocator_provider")
    @patch("vhf.services.allocation_service.get_db_strat")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_ai_weighted_accepts_list_response_and_forwards_context(
        self,
        mock_get_portfolio,
        mock_get_strat,
        mock_resolve_provider,
        mock_record,
    ):
        provider = FakeProvider(response=[3.0, 1.0], name="local:test")
        mock_resolve_provider.return_value = (AIProviderMode.local, provider)
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=5,
            portfolio_name="p5",
            strategies=["s1", "s2"],
            weights=[0.4, 0.6],
            live=False,
        )
        mock_get_strat.side_effect = [
            StrategyPrice(strategy_id="s1", name="S1", description="", category="eq", prices=[1, 2, 3]),
            StrategyPrice(strategy_id="s2", name="S2", description="", category="eq", prices=[2, 4, 8]),
        ]

        result = allocate_portfolio(
            AllocationRequest(
                portfolio_id=5,
                method=AllocationMethod.ai_weighted,
                ai_timeout_seconds=7.5,
                ai_context={"risk_profile": "balanced"},
            )
        )

        self.assertFalse(result.fallback_applied)
        self.assertEqual(result.ai_provider_mode, AIProviderMode.local)
        self.assertEqual(result.ai_provider_name, "local:test")
        self.assertIsNone(result.ai_provider_error)
        self.assertAlmostEqual(result.target_weights[0], 0.75)
        self.assertAlmostEqual(result.target_weights[1], 0.25)
        self.assertEqual(provider.last_timeout, 7.5)
        self.assertEqual(provider.last_context["request_context"], {"risk_profile": "balanced"})
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.resolve_allocator_provider")
    @patch("vhf.services.allocation_service.get_db_strat")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_ai_weighted_accepts_allocations_map(
        self,
        mock_get_portfolio,
        mock_get_strat,
        mock_resolve_provider,
        mock_record,
    ):
        provider = FakeProvider(response={"allocations": {"s2": 0.8, "s1": 0.2}}, name="remote:test")
        mock_resolve_provider.return_value = (AIProviderMode.remote, provider)
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=6,
            portfolio_name="p6",
            strategies=["s1", "s2"],
            weights=None,
            live=False,
        )
        mock_get_strat.side_effect = [
            StrategyPrice(strategy_id="s1", name="S1", description="", category="eq", prices=[1]),
            StrategyPrice(strategy_id="s2", name="S2", description="", category="eq", prices=[1]),
        ]

        result = allocate_portfolio(
            AllocationRequest(
                portfolio_id=6,
                method=AllocationMethod.ai_weighted,
            )
        )

        self.assertFalse(result.fallback_applied)
        self.assertAlmostEqual(result.target_weights[0], 0.2)
        self.assertAlmostEqual(result.target_weights[1], 0.8)
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.resolve_allocator_provider")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_ai_weighted_falls_back_when_provider_fails(
        self,
        mock_get_portfolio,
        mock_resolve_provider,
        mock_record,
    ):
        provider = FakeProvider(error=RuntimeError("upstream timeout"), name="remote:test")
        mock_resolve_provider.return_value = (AIProviderMode.remote, provider)
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=7,
            portfolio_name="p7",
            strategies=["s1", "s2"],
            weights=None,
            live=False,
        )

        result = allocate_portfolio(
            AllocationRequest(
                portfolio_id=7,
                method=AllocationMethod.ai_weighted,
            )
        )

        self.assertTrue(result.fallback_applied)
        self.assertEqual(result.fallback_reason, "ai_weighted provider failed; used equal_weight fallback")
        self.assertEqual(result.target_weights, [0.5, 0.5])
        self.assertIn("upstream timeout", result.ai_provider_error)
        mock_record.assert_called_once()

    @patch("vhf.services.allocation_service.record_allocation_snapshot")
    @patch("vhf.services.allocation_service.resolve_allocator_provider")
    @patch("vhf.services.allocation_service.get_db_portfolio_id")
    def test_ai_weighted_strict_mode_raises_on_provider_failure(
        self,
        mock_get_portfolio,
        mock_resolve_provider,
        mock_record,
    ):
        provider = FakeProvider(error=RuntimeError("service unavailable"), name="remote:test")
        mock_resolve_provider.return_value = (AIProviderMode.remote, provider)
        mock_get_portfolio.return_value = Portfolio(
            portfolio_id=8,
            portfolio_name="p8",
            strategies=["s1", "s2"],
            weights=None,
            live=False,
        )

        with self.assertRaises(AllocationServiceError) as ctx:
            allocate_portfolio(
                AllocationRequest(
                    portfolio_id=8,
                    method=AllocationMethod.ai_weighted,
                    ai_strict=True,
                )
            )

        self.assertIn("strict mode", str(ctx.exception))
        mock_record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
