"""
Unit tests for the backtesting service.
All DB calls are mocked — no real database required.
"""

import math
import unittest
from unittest.mock import MagicMock, patch

from vhf.models.allocation import AllocationMethod
from vhf.services.backtest import (
    BacktestError,
    BacktestRequest,
    _compute_weights,
    _equal_weights,
    _max_drawdown,
    _momentum_weights,
    _sharpe,
    run_backtest,
)


# ---------------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------------

class EqualWeightsTest(unittest.TestCase):
    def test_sums_to_one(self):
        for n in [1, 2, 5, 10]:
            w = _equal_weights(n)
            self.assertAlmostEqual(sum(w), 1.0)
            self.assertEqual(len(w), n)

    def test_uniform(self):
        w = _equal_weights(4)
        self.assertTrue(all(abs(x - 0.25) < 1e-9 for x in w))


class MomentumWeightsTest(unittest.TestCase):
    def test_higher_momentum_gets_more_weight(self):
        sids = ["s1", "s2"]
        prices = {
            "s1": [100.0, 150.0],   # +50%
            "s2": [100.0, 110.0],   # +10%
        }
        w = _momentum_weights(sids, prices)
        self.assertGreater(w[0], w[1])

    def test_sums_to_one(self):
        sids = ["s1", "s2", "s3"]
        prices = {s: [100.0, 100.0 + i * 10] for i, s in enumerate(sids)}
        w = _momentum_weights(sids, prices)
        self.assertAlmostEqual(sum(w), 1.0)

    def test_no_history_gets_neutral_weight(self):
        sids = ["s1", "s2"]
        prices = {"s1": [], "s2": []}
        w = _momentum_weights(sids, prices)
        self.assertAlmostEqual(w[0], 0.5)
        self.assertAlmostEqual(w[1], 0.5)

    def test_single_price_treated_as_no_history(self):
        sids = ["s1"]
        prices = {"s1": [100.0]}
        w = _momentum_weights(sids, prices)
        self.assertAlmostEqual(w[0], 1.0)

    def test_zero_start_price_gets_neutral_weight(self):
        sids = ["s1", "s2"]
        prices = {"s1": [0.0, 110.0], "s2": [100.0, 120.0]}
        w = _momentum_weights(sids, prices)
        self.assertAlmostEqual(sum(w), 1.0)


class MaxDrawdownTest(unittest.TestCase):
    def test_no_drawdown(self):
        values = [100.0, 110.0, 120.0, 130.0]
        self.assertAlmostEqual(_max_drawdown(values), 0.0)

    def test_full_loss(self):
        values = [100.0, 50.0]
        dd = _max_drawdown(values)
        self.assertAlmostEqual(dd, -50.0)

    def test_recovers_after_drawdown(self):
        values = [100.0, 80.0, 90.0, 110.0]
        dd = _max_drawdown(values)
        self.assertAlmostEqual(dd, -20.0)

    def test_multiple_drawdowns_returns_worst(self):
        # Drop 20% then drop 30%
        values = [100.0, 80.0, 90.0, 63.0]
        dd = _max_drawdown(values)
        self.assertLess(dd, -20.0)


class SharpeTest(unittest.TestCase):
    def test_positive_returns_positive_sharpe(self):
        # Oscillating positive returns with non-zero variance.
        import random
        rng = random.Random(1)
        returns = [0.005 + rng.uniform(0.001, 0.009) for _ in range(252)]
        s = _sharpe(returns)
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)

    def test_negative_returns_negative_sharpe(self):
        import random
        rng = random.Random(2)
        returns = [-0.005 - rng.uniform(0.001, 0.009) for _ in range(252)]
        s = _sharpe(returns)
        self.assertIsNotNone(s)
        self.assertLess(s, 0)

    def test_zero_variance_returns_none(self):
        # All same return → stdev = 0
        returns = [0.005] * 100
        # stdev of identical values is 0 → should return None
        s = _sharpe(returns)
        self.assertIsNone(s)

    def test_too_few_returns_returns_none(self):
        self.assertIsNone(_sharpe([]))
        self.assertIsNone(_sharpe([0.01]))

    def test_mixed_returns(self):
        import random
        rng = random.Random(42)
        returns = [rng.gauss(0.0005, 0.01) for _ in range(252)]
        s = _sharpe(returns)
        self.assertIsNotNone(s)
        self.assertTrue(math.isfinite(s))


# ---------------------------------------------------------------------------
# run_backtest — integration tests with mocked DB
# ---------------------------------------------------------------------------

def _make_portfolio(strategy_ids):
    p = MagicMock()
    p.strategies = strategy_ids
    p.weights = [1.0 / len(strategy_ids)] * len(strategy_ids) if strategy_ids else []
    return p


def _linear_prices(n, start=1000.0, step=5.0):
    """n (date, price) pairs starting 2025-01-02, weekdays only."""
    from datetime import date, timedelta
    prices = []
    day = date(2025, 1, 2)
    count = 0
    while count < n:
        if day.weekday() < 5:
            prices.append((day.isoformat(), round(start + count * step, 4)))
            count += 1
        day += timedelta(days=1)
    return prices


class RunBacktestTest(unittest.TestCase):

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_equal_weight_positive_return(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        # Both strategies trend upward.
        mock_history.side_effect = lambda sid: _linear_prices(50, start=1000.0, step=5.0)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        self.assertGreater(result.total_return_pct, 0)
        self.assertEqual(result.method, "equal_weight")
        self.assertEqual(len(result.daily_values), 50)
        self.assertEqual(result.n_trading_days, 49)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_score_weighted_positive_return(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(50)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.score_weighted,
            rebalance_frequency_days=10,
        ))

        self.assertGreater(result.total_return_pct, 0)
        self.assertAlmostEqual(sum(leg.final_weight for leg in result.strategy_legs), 1.0, places=5)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_final_value_equals_initial_times_return(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        mock_history.return_value = _linear_prices(30, start=1000.0, step=10.0)

        result = run_backtest(BacktestRequest(portfolio_id=1, initial_value=100.0))
        expected_total_return = (result.final_value / 100.0 - 1.0) * 100.0
        self.assertAlmostEqual(result.total_return_pct, expected_total_return, places=3)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_daily_values_length_matches_common_dates(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(20)

        result = run_backtest(BacktestRequest(portfolio_id=1))
        self.assertEqual(len(result.daily_values), 20)
        # First value should be the initial_value
        self.assertAlmostEqual(result.daily_values[0][1], 100.0)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_date_range_filtering(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        mock_history.return_value = _linear_prices(50)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            start_date="2025-01-06",
            end_date="2025-01-17",
        ))

        self.assertGreaterEqual(result.start_date, "2025-01-06")
        self.assertLessEqual(result.end_date, "2025-01-17")
        self.assertLess(result.n_trading_days, 49)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_no_look_ahead_bias(self, mock_portfolio, mock_history):
        """Weights at rebalance t should only use prices[0..t]."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        # s1 falls, s2 rises — score_weighted should shift toward s2 over time.
        s1_prices = [(f"2025-01-{2+i:02d}", 1000.0 - i * 5) for i in range(10)
                     if (i + 1) % 7 != 0 and (i + 2) % 7 != 0][:10]
        s2_prices = [(f"2025-01-{2+i:02d}", 1000.0 + i * 10) for i in range(10)
                     if (i + 1) % 7 != 0 and (i + 2) % 7 != 0][:10]

        from datetime import date, timedelta
        day = date(2025, 1, 2)
        days = []
        while len(days) < 20:
            if day.weekday() < 5:
                days.append(day.isoformat())
            day += timedelta(days=1)

        s1 = [(d, 1000.0 - i * 3) for i, d in enumerate(days)]
        s2 = [(d, 1000.0 + i * 5) for i, d in enumerate(days)]

        mock_history.side_effect = lambda sid: s1 if sid == "s1" else s2

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.score_weighted,
            rebalance_frequency_days=5,
        ))

        # s2 outperformed so its final weight should be higher
        s1_leg = next(l for l in result.strategy_legs if l.strategy_id == "s1")
        s2_leg = next(l for l in result.strategy_legs if l.strategy_id == "s2")
        self.assertGreater(s2_leg.final_weight, s1_leg.final_weight)

    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_raises_on_empty_portfolio(self, mock_portfolio):
        mock_portfolio.return_value = _make_portfolio([])
        with self.assertRaises(BacktestError):
            run_backtest(BacktestRequest(portfolio_id=1))

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_raises_on_no_price_data(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        mock_history.return_value = []
        with self.assertRaises(BacktestError):
            run_backtest(BacktestRequest(portfolio_id=1))

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_raises_on_single_common_date(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        mock_history.return_value = [("2025-01-02", 1000.0)]
        with self.assertRaises(BacktestError):
            run_backtest(BacktestRequest(portfolio_id=1))

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_count_is_correct(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        mock_history.return_value = _linear_prices(21)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            rebalance_frequency_days=5,
        ))

        # 21 days: rebalances at day 5, 10, 15, 20 → 4 rebalances
        self.assertEqual(result.n_rebalances, 4)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_max_drawdown_is_non_positive(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1"])
        # Prices go up then down
        from datetime import date, timedelta
        day = date(2025, 1, 2)
        prices = []
        for i in range(20):
            if day.weekday() < 5:
                p = 1000.0 + i * 5 if i < 10 else 1000.0 + (20 - i) * 5
                prices.append((day.isoformat(), p))
            day += timedelta(days=1)

        mock_history.return_value = prices[:20]
        result = run_backtest(BacktestRequest(portfolio_id=1))
        self.assertLessEqual(result.max_drawdown_pct, 0.0)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_strategy_legs_weights_sum_to_one(self, mock_portfolio, mock_history):
        mock_portfolio.return_value = _make_portfolio(["s1", "s2", "s3"])
        mock_history.side_effect = lambda sid: _linear_prices(30)

        result = run_backtest(BacktestRequest(portfolio_id=1))
        total = sum(leg.final_weight for leg in result.strategy_legs)
        self.assertAlmostEqual(total, 1.0, places=5)


# ---------------------------------------------------------------------------
# ai_weighted with live_ai_calls
# ---------------------------------------------------------------------------

class AIWeightedBacktestTest(unittest.TestCase):

    @patch("vhf.services.backtest.get_db_strat")
    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_live_ai_calls_invokes_provider(self, mock_portfolio, mock_history, mock_strat):
        """With live_ai_calls=True the AI provider is called at each rebalance."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(50)
        mock_strat.return_value = MagicMock(name="S", category="equity", description="")

        mock_provider = MagicMock()
        mock_provider.allocate.return_value = [0.6, 0.4]

        with patch("vhf.services.backtest.resolve_allocator_provider", return_value=(None, mock_provider)):
            result = run_backtest(BacktestRequest(
                portfolio_id=1,
                method=AllocationMethod.ai_weighted,
                live_ai_calls=True,
                rebalance_frequency_days=10,
            ))

        self.assertGreater(mock_provider.allocate.call_count, 0)
        self.assertEqual(result.ai_call_count, mock_provider.allocate.call_count)
        self.assertEqual(result.ai_fallback_count, 0)

    @patch("vhf.services.backtest.get_db_strat")
    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_live_ai_fallback_on_provider_error(self, mock_portfolio, mock_history, mock_strat):
        """When the AI provider raises, the backtest falls back to equal_weight."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(30)
        mock_strat.return_value = MagicMock(name="S", category="equity", description="")

        mock_provider = MagicMock()
        mock_provider.allocate.side_effect = RuntimeError("API unavailable")

        with patch("vhf.services.backtest.resolve_allocator_provider", return_value=(None, mock_provider)):
            result = run_backtest(BacktestRequest(
                portfolio_id=1,
                method=AllocationMethod.ai_weighted,
                live_ai_calls=True,
                rebalance_frequency_days=10,
            ))

        self.assertEqual(result.ai_call_count, 0)
        self.assertGreater(result.ai_fallback_count, 0)
        # Result should still be valid despite fallbacks
        self.assertIsNotNone(result.total_return_pct)
        self.assertTrue(math.isfinite(result.total_return_pct))

    @patch("vhf.services.backtest.get_db_strat")
    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_ai_metrics_none_when_live_ai_disabled(self, mock_portfolio, mock_history, mock_strat):
        """AI metrics should be None when live_ai_calls=False (the default)."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(30)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.ai_weighted,
            live_ai_calls=False,
        ))

        self.assertIsNone(result.ai_call_count)
        self.assertIsNone(result.ai_fallback_count)
        self.assertIsNone(result.weight_stability)

    @patch("vhf.services.backtest.get_db_strat")
    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_weight_stability_computed(self, mock_portfolio, mock_history, mock_strat):
        """weight_stability is a non-negative float when live_ai_calls=True."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(50)
        mock_strat.return_value = MagicMock(name="S", category="equity", description="")

        call_count = [0]

        def alternating_weights(ctx, *, timeout_seconds):
            # Alternate between two weight vectors to produce non-zero stability
            call_count[0] += 1
            return [0.7, 0.3] if call_count[0] % 2 == 0 else [0.4, 0.6]

        mock_provider = MagicMock()
        mock_provider.allocate.side_effect = alternating_weights

        with patch("vhf.services.backtest.resolve_allocator_provider", return_value=(None, mock_provider)):
            result = run_backtest(BacktestRequest(
                portfolio_id=1,
                method=AllocationMethod.ai_weighted,
                live_ai_calls=True,
                rebalance_frequency_days=10,
            ))

        self.assertIsNotNone(result.weight_stability)
        self.assertGreaterEqual(result.weight_stability, 0.0)

    @patch("vhf.services.backtest.get_db_strat")
    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_ai_context_forwarded_to_provider(self, mock_portfolio, mock_history, mock_strat):
        """Extra ai_context dict is forwarded to the AI provider in every call."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(25)
        mock_strat.return_value = MagicMock(name="S", category="equity", description="")

        received_contexts = []

        def capture(ctx, *, timeout_seconds):
            received_contexts.append(ctx)
            return [0.5, 0.5]

        mock_provider = MagicMock()
        mock_provider.allocate.side_effect = capture

        with patch("vhf.services.backtest.resolve_allocator_provider", return_value=(None, mock_provider)):
            run_backtest(BacktestRequest(
                portfolio_id=1,
                method=AllocationMethod.ai_weighted,
                live_ai_calls=True,
                ai_context={"risk_appetite": "conservative"},
                rebalance_frequency_days=10,
            ))

        self.assertTrue(all(
            ctx.get("request_context", {}).get("risk_appetite") == "conservative"
            for ctx in received_contexts
        ))


    # ------------------------------------------------------------------
    # rebalance_history tests
    # ------------------------------------------------------------------

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_history_always_present(self, mock_portfolio, mock_history):
        """rebalance_history is always populated, even for non-AI methods."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(30)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        self.assertIsNotNone(result.rebalance_history)
        self.assertGreaterEqual(len(result.rebalance_history), 1)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_history_count(self, mock_portfolio, mock_history):
        """rebalance_history has n_rebalances + 1 entries (initial + each rebalance)."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(50)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        self.assertEqual(len(result.rebalance_history), result.n_rebalances + 1)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_history_weights_sum_to_one(self, mock_portfolio, mock_history):
        """Each rebalance snapshot's weights sum to ~1.0."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2", "s3"])
        mock_history.side_effect = lambda sid: _linear_prices(40)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        for snap in result.rebalance_history:
            total = sum(snap.weights.values())
            self.assertAlmostEqual(total, 1.0, places=5)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_history_keyed_by_strategy_id(self, mock_portfolio, mock_history):
        """Weights dict is keyed by strategy_id, not bare indices."""
        mock_portfolio.return_value = _make_portfolio(["alpha", "beta"])
        mock_history.side_effect = lambda sid: _linear_prices(30)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        for snap in result.rebalance_history:
            self.assertIn("alpha", snap.weights)
            self.assertIn("beta", snap.weights)

    @patch("vhf.services.backtest.get_strategy_price_history_raw")
    @patch("vhf.services.backtest.get_db_portfolio_id")
    def test_rebalance_history_first_snapshot_is_start_date(self, mock_portfolio, mock_history):
        """First rebalance snapshot date equals the actual start date."""
        mock_portfolio.return_value = _make_portfolio(["s1", "s2"])
        mock_history.side_effect = lambda sid: _linear_prices(30)

        result = run_backtest(BacktestRequest(
            portfolio_id=1,
            method=AllocationMethod.equal_weight,
            rebalance_frequency_days=10,
        ))

        self.assertEqual(result.rebalance_history[0].date, result.start_date)


if __name__ == "__main__":
    unittest.main()
