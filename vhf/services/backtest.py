"""
Portfolio backtesting service.

Simulates a portfolio strategy over historical price data, computing
performance metrics (total return, annualised return, Sharpe ratio,
max drawdown) for different allocation methods.

No look-ahead bias: weights at each rebalance date are computed using
only price data up to and including that date.

For ai_weighted with live_ai_calls=True the allocator is called once per
rebalance date using only the prices visible at that point.  Set
live_ai_calls=False (the default) to use score_weighted as a fast proxy
instead of incurring API calls.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from vhf.models.allocation import AllocationMethod
from vhf.ai.weight_allocator_provider import resolve_allocator_provider
from vhf.db.operations import (
    get_db_portfolio_id,
    get_db_strat,
    get_strategy_price_history_raw,
)


class BacktestRequest(BaseModel):
    portfolio_id: int
    method: AllocationMethod = AllocationMethod.equal_weight
    start_date: str | None = None          # ISO date; defaults to earliest common date
    end_date: str | None = None            # ISO date; defaults to latest common date
    rebalance_frequency_days: int = Field(default=21, ge=1)  # approx monthly
    initial_value: float = Field(default=100.0, gt=0)
    # AI backtest options (only relevant when method=ai_weighted)
    live_ai_calls: bool = False            # If True, call the AI allocator at each rebalance
    ai_context: dict | None = None        # Extra context forwarded to the AI allocator
    ai_timeout_seconds: float = Field(default=30.0, gt=0)


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
    # AI-specific metrics (None for non-AI methods or when live_ai_calls=False)
    ai_call_count: int | None = None
    ai_fallback_count: int | None = None
    weight_stability: float | None = None  # avg per-strategy weight std dev across rebalances


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
    # ai_weighted without live calls: fall back to score_weighted
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


def _build_backtest_ai_context(
    strategy_ids: list[str],
    strategy_meta: dict[str, dict],
    prices_up_to: dict[str, list[float]],
    current_weights: list[float],
    extra_context: dict | None,
) -> dict[str, Any]:
    """Build the context dict passed to the AI allocator at each rebalance."""
    strategy_data = []
    for sid in strategy_ids:
        prices = prices_up_to.get(sid, [])
        meta = strategy_meta.get(sid, {})
        strategy_data.append({
            "strategy_id": sid,
            "name": meta.get("name", sid),
            "category": meta.get("category", ""),
            "description": meta.get("description", ""),
            "prices": prices[-20:] if len(prices) > 20 else prices,
            "latest_price": prices[-1] if prices else None,
            "price_count": len(prices),
        })

    ctx: dict[str, Any] = {
        "strategies": strategy_ids,
        "strategy_data": strategy_data,
        "current_weights": current_weights,
    }
    if extra_context:
        ctx["request_context"] = extra_context
    return ctx


def _parse_ai_weights(response: Any, n: int) -> list[float]:
    """Normalize raw AI provider output into a weight vector of length n."""
    if isinstance(response, (list, tuple)) and len(response) == n:
        weights = [float(v) for v in response]
        total = sum(weights)
        if total > 0 and all(w >= 0 for w in weights):
            return [w / total for w in weights]
    raise ValueError(f"Cannot extract {n} non-negative weights from AI response: {response!r}")


def _weight_stability(weight_history: list[list[float]]) -> float | None:
    """
    Average per-strategy weight std dev across rebalances.
    Lower = more stable / consistent AI allocation decisions.
    Returns None if fewer than 2 rebalances recorded.
    """
    if len(weight_history) < 2:
        return None
    n = len(weight_history[0])
    stdevs = []
    for j in range(n):
        vals = [wh[j] for wh in weight_history]
        stdevs.append(statistics.stdev(vals))
    return round(statistics.mean(stdevs), 6) if stdevs else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(request: BacktestRequest) -> BacktestResult:
    """
    Run a historical backtest for a portfolio using stored price data.

    Args:
        request: BacktestRequest with portfolio_id, method, date range,
                 rebalance frequency, and initial capital.
                 Set live_ai_calls=True with method=ai_weighted to call the
                 AI allocator at each rebalance date (incurs API calls).

    Returns:
        BacktestResult with performance metrics and daily portfolio values.

    Raises:
        BacktestError: If the portfolio has no strategies, no price data,
                       or the requested date range is too short.
    """
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

    # ---------------------------------------------------------------------------
    # AI provider setup (only when live_ai_calls=True and method=ai_weighted)
    # ---------------------------------------------------------------------------
    use_live_ai = (
        request.method == AllocationMethod.ai_weighted
        and request.live_ai_calls
    )
    ai_provider = None
    strategy_meta: dict[str, dict] = {}
    if use_live_ai:
        _, ai_provider = resolve_allocator_provider(None)
        for sid in strategy_ids:
            try:
                strat = get_db_strat(sid)
                strategy_meta[sid] = {
                    "name": strat.name,
                    "category": strat.category,
                    "description": strat.description,
                }
            except Exception:
                strategy_meta[sid] = {"name": sid, "category": "", "description": ""}

    ai_call_count = 0
    ai_fallback_count = 0
    weight_history: list[list[float]] = []

    def _resolve_weights(
        prices_up_to: dict[str, list[float]],
        current_weights: list[float],
    ) -> list[float]:
        nonlocal ai_call_count, ai_fallback_count
        if ai_provider is not None:
            ctx = _build_backtest_ai_context(
                strategy_ids,
                strategy_meta,
                prices_up_to,
                current_weights,
                request.ai_context,
            )
            try:
                raw = ai_provider.allocate(ctx, timeout_seconds=request.ai_timeout_seconds)
                weights = _parse_ai_weights(raw, n)
                ai_call_count += 1
                return weights
            except Exception:
                ai_fallback_count += 1
                return _equal_weights(n)
        return _compute_weights(request.method, strategy_ids, prices_up_to, portfolio.weights)

    # ---------------------------------------------------------------------------
    # Simulation loop
    # ---------------------------------------------------------------------------

    # Initialise: compute first weights at day 0 using only day-0 prices.
    initial_prices_up_to = {sid: [price_by_sid[sid][0]] for sid in strategy_ids}
    weights = _resolve_weights(initial_prices_up_to, _equal_weights(n))
    weight_history.append(weights)

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
            weights = _resolve_weights(prices_up_to, weights)
            weight_history.append(weights)
            holdings = [w * portfolio_value for w in weights]
            n_rebalances += 1
            last_rebalance_idx = i

    # ---------------------------------------------------------------------------
    # Compute final metrics
    # ---------------------------------------------------------------------------
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
    sharpe = _sharpe(daily_returns)

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
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown_pct=round(_max_drawdown(portfolio_vals), 4),
        strategy_legs=strategy_legs,
        daily_values=daily_values,
        ai_call_count=ai_call_count if use_live_ai else None,
        ai_fallback_count=ai_fallback_count if use_live_ai else None,
        weight_stability=_weight_stability(weight_history) if use_live_ai else None,
    )
