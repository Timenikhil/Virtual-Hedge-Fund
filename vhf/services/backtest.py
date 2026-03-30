"""
Portfolio backtesting service.

Simulates a portfolio strategy over historical price data, computing
performance metrics (total return, annualised return, Sharpe ratio,
max drawdown) for different allocation methods.

No look-ahead bias: weights at each rebalance date are computed using
only price data up to and including that date.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from vhf.models.allocation import AllocationMethod


class BacktestRequest(BaseModel):
    portfolio_id: int
    method: AllocationMethod = AllocationMethod.equal_weight
    start_date: str | None = None          # ISO date; defaults to earliest common date
    end_date: str | None = None            # ISO date; defaults to latest common date
    rebalance_frequency_days: int = Field(default=21, ge=1)  # approx monthly
    initial_value: float = Field(default=100.0, gt=0)


class BacktestLeg(BaseModel):
    """Per-strategy snapshot at the end of the backtest."""
    strategy_id: str
    final_weight: float
    total_return_pct: float


class BacktestResult(BaseModel):
    portfolio_id: int
    method: str
    start_date: str
    end_date: str
    n_trading_days: int
    n_rebalances: int
    initial_value: float
    final_value: float
    total_return_pct: float
    annualised_return_pct: float
    sharpe_ratio: float | None      # None when fewer than 2 daily returns
    max_drawdown_pct: float
    strategy_legs: list[BacktestLeg]
    daily_values: list[tuple[str, float]]  # (ISO date, portfolio value)


class BacktestError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _equal_weights(n: int) -> list[float]:
    return [1.0 / n] * n


def _momentum_weights(
    strategy_ids: list[str],
    prices_up_to: dict[str, list[float]],
) -> list[float]:
    """
    Score-weighted allocation: weight proportional to end-to-end price momentum
    up to the current rebalance date. Strategies with no history get weight 1.0.
    """
    scores: list[float] = []
    for sid in strategy_ids:
        prices = prices_up_to.get(sid, [])
        if len(prices) < 2 or prices[0] <= 0:
            scores.append(1.0)
        else:
            ratio = prices[-1] / prices[0]
            scores.append(max(ratio, 0.01))
    total = sum(scores)
    if total <= 0:
        return _equal_weights(len(strategy_ids))
    return [s / total for s in scores]


def _compute_weights(
    method: AllocationMethod,
    strategy_ids: list[str],
    prices_up_to: dict[str, list[float]],
    stored_weights: list[float] | None,
) -> list[float]:
    n = len(strategy_ids)
    if method == AllocationMethod.equal_weight:
        return _equal_weights(n)
    if method == AllocationMethod.score_weighted:
        return _momentum_weights(strategy_ids, prices_up_to)
    if method == AllocationMethod.manual:
        if stored_weights and len(stored_weights) == n:
            total = sum(stored_weights)
            if total > 0:
                return [w / total for w in stored_weights]
        return _equal_weights(n)
    # ai_weighted: fall back to score_weighted (no live Claude calls during backtest)
    return _momentum_weights(strategy_ids, prices_up_to)


def _sharpe(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 2:
        return None
    mean = statistics.mean(daily_returns)
    stdev = statistics.stdev(daily_returns)
    if stdev == 0:
        return None
    return (mean / stdev) * math.sqrt(252)


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0  # percent, negative


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(request: BacktestRequest) -> BacktestResult:
    """
    Run a historical backtest for a portfolio using stored price data.

    Args:
        request: BacktestRequest with portfolio_id, method, date range,
                 rebalance frequency, and initial capital.

    Returns:
        BacktestResult with performance metrics and daily portfolio values.

    Raises:
        BacktestError: If the portfolio has no strategies, no price data,
                       or the requested date range is too short.
    """
    # Late import to avoid circular imports at module load time.
    from vhf.db.operations import (
        get_db_portfolio_id,
        get_strategy_price_history_raw,
    )

    portfolio = get_db_portfolio_id(request.portfolio_id)
    strategy_ids = portfolio.strategies
    if not strategy_ids:
        raise BacktestError("Portfolio has no strategies to backtest.")

    # Load full price histories.
    raw_histories: dict[str, dict[str, float]] = {}
    for sid in strategy_ids:
        pairs = get_strategy_price_history_raw(sid)
        raw_histories[sid] = {ts: price for ts, price in pairs}

    # Find the common date range across all strategies.
    date_sets = [set(raw_histories[sid].keys()) for sid in strategy_ids if raw_histories[sid]]
    if not date_sets:
        raise BacktestError("No price history found for any strategy in this portfolio.")

    common_dates_str = sorted(set.intersection(*date_sets))
    if len(common_dates_str) < 2:
        raise BacktestError(
            f"Insufficient overlapping price history across all strategies "
            f"(only {len(common_dates_str)} common dates)."
        )

    # Apply caller-supplied date range clipping.
    if request.start_date:
        common_dates_str = [d for d in common_dates_str if d >= request.start_date]
    if request.end_date:
        common_dates_str = [d for d in common_dates_str if d <= request.end_date]

    if len(common_dates_str) < 2:
        raise BacktestError("Date range too narrow: fewer than 2 common trading days after filtering.")

    actual_start = common_dates_str[0]
    actual_end = common_dates_str[-1]

    # Build per-strategy ordered price arrays (aligned to common dates).
    price_by_sid: dict[str, list[float]] = {
        sid: [raw_histories[sid][d] for d in common_dates_str]
        for sid in strategy_ids
    }

    n = len(strategy_ids)
    freq = max(1, request.rebalance_frequency_days)

    # Initialise: compute first weights at day 0 using only day-0 prices.
    initial_prices_up_to = {sid: [price_by_sid[sid][0]] for sid in strategy_ids}
    weights = _compute_weights(
        request.method, strategy_ids, initial_prices_up_to, portfolio.weights
    )

    # Holdings = value allocated to each strategy.
    holdings = [w * request.initial_value for w in weights]
    portfolio_value = request.initial_value

    daily_values: list[tuple[str, float]] = [(actual_start, portfolio_value)]
    daily_returns: list[float] = []
    n_rebalances = 0
    last_rebalance_idx = 0

    for i in range(1, len(common_dates_str)):
        day_str = common_dates_str[i]

        # Update each holding by the strategy's daily return.
        new_holdings: list[float] = []
        for j, sid in enumerate(strategy_ids):
            prev_price = price_by_sid[sid][i - 1]
            curr_price = price_by_sid[sid][i]
            if prev_price > 0:
                daily_ret = curr_price / prev_price
            else:
                daily_ret = 1.0
            new_holdings.append(holdings[j] * daily_ret)

        holdings = new_holdings
        new_value = sum(holdings)

        if new_value > 0:
            daily_returns.append(new_value / portfolio_value - 1.0)
        portfolio_value = new_value
        daily_values.append((day_str, round(portfolio_value, 6)))

        # Rebalance if due.
        if (i - last_rebalance_idx) >= freq:
            prices_up_to = {
                sid: price_by_sid[sid][: i + 1]
                for sid in strategy_ids
            }
            weights = _compute_weights(
                request.method, strategy_ids, prices_up_to, portfolio.weights
            )
            holdings = [w * portfolio_value for w in weights]
            n_rebalances += 1
            last_rebalance_idx = i

    # Compute final metrics.
    final_value = portfolio_value
    total_return = (final_value / request.initial_value - 1.0) * 100.0

    n_days = len(common_dates_str) - 1
    if n_days > 0:
        annualised = ((final_value / request.initial_value) ** (252.0 / n_days) - 1.0) * 100.0
    else:
        annualised = 0.0

    # Final weights.
    total_holdings = sum(holdings)
    final_weights = [h / total_holdings for h in holdings] if total_holdings > 0 else _equal_weights(n)

    strategy_legs = []
    for j, sid in enumerate(strategy_ids):
        prices = price_by_sid[sid]
        strat_return = (prices[-1] / prices[0] - 1.0) * 100.0 if prices[0] > 0 else 0.0
        strategy_legs.append(BacktestLeg(
            strategy_id=sid,
            final_weight=round(final_weights[j], 6),
            total_return_pct=round(strat_return, 4),
        ))

    portfolio_vals = [v for _, v in daily_values]

    return BacktestResult(
        portfolio_id=request.portfolio_id,
        method=request.method.value,
        start_date=actual_start,
        end_date=actual_end,
        n_trading_days=n_days,
        n_rebalances=n_rebalances,
        initial_value=request.initial_value,
        final_value=round(final_value, 6),
        total_return_pct=round(total_return, 4),
        annualised_return_pct=round(annualised, 4),
        sharpe_ratio=round(_sharpe(daily_returns), 4) if _sharpe(daily_returns) is not None else None,
        max_drawdown_pct=round(_max_drawdown(portfolio_vals), 4),
        strategy_legs=strategy_legs,
        daily_values=daily_values,
    )
