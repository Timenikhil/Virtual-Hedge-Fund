from __future__ import annotations

import math
from datetime import datetime, timezone

from vhf.db.operations import (
    get_db_portfolio_id,
    get_portfolio_account,
    record_rebalance_run,
    update_portfolio_weights,
)
from vhf.logging.log import logger
from vhf.models.allocation import AllocationRequest
from vhf.models.rebalance import RebalanceLeg, RebalancePlan, RebalanceRequest
from vhf.services.allocation_service import AllocationServiceError, allocate_portfolio


class RebalanceEngineError(ValueError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _equal_weights(n: int) -> list[float]:
    if n <= 0:
        raise RebalanceEngineError("Cannot rebalance a portfolio with zero strategies.")
    return [1.0 / n] * n


def _normalize(weights: list[float], expected_len: int, label: str) -> list[float]:
    # Normalize and validate vectors so drift math always operates on clean probability vectors.
    if len(weights) != expected_len:
        raise RebalanceEngineError(
            f"{label} length mismatch: expected {expected_len}, got {len(weights)}."
        )

    normalized: list[float] = []
    for idx, value in enumerate(weights):
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise RebalanceEngineError(f"{label}[{idx}] is not numeric: {value!r}") from exc

        if not math.isfinite(num):
            raise RebalanceEngineError(f"{label}[{idx}] is not finite: {num!r}")
        if num < 0:
            raise RebalanceEngineError(f"{label}[{idx}] is negative: {num!r}")

        normalized.append(num)

    total = sum(normalized)
    if total <= 0:
        raise RebalanceEngineError(f"{label} sum must be > 0.")

    return [value / total for value in normalized]


def build_rebalance_plan(request: RebalanceRequest) -> RebalancePlan:
    if request.threshold < 0 or not math.isfinite(request.threshold):
        raise RebalanceEngineError("threshold must be a finite, non-negative number.")

    portfolio = get_db_portfolio_id(request.portfolio_id)
    strategies = portfolio.strategies
    if not strategies:
        raise RebalanceEngineError("Portfolio has no strategies to rebalance.")

    allocation = allocate_portfolio(
        AllocationRequest(
            portfolio_id=request.portfolio_id,
            method=request.method,
            raw_weights=request.allocation_raw_weights,
            ai_provider_mode=request.ai_provider_mode,
            ai_strict=request.ai_strict,
            ai_timeout_seconds=request.ai_timeout_seconds,
            ai_context=request.ai_context,
            persist=False,
        )
    )

    n = len(strategies)
    current_source = request.current_weights
    if current_source is None:
        # If caller does not supply current weights, use stored portfolio state as the current book.
        current_source = portfolio.weights if portfolio.weights else _equal_weights(n)

    current_weights = _normalize(current_source, n, "current_weights")
    target_weights = _normalize(allocation.target_weights, n, "target_weights")

    legs: list[RebalanceLeg] = []
    abs_deltas: list[float] = []
    rebalance_required = False

    for strategy_id, current, target in zip(strategies, current_weights, target_weights):
        delta = target - current
        abs_delta = abs(delta)
        # Threshold gates micro-adjustments to avoid over-trading small drifts.
        trade_weight = delta if abs_delta >= request.threshold else 0.0

        if trade_weight > 0:
            action = "buy"
        elif trade_weight < 0:
            action = "sell"
        else:
            action = "hold"

        if trade_weight != 0:
            rebalance_required = True

        abs_deltas.append(abs_delta)
        legs.append(
            RebalanceLeg(
                strategy_id=strategy_id,
                current_weight=current,
                target_weight=target,
                delta_weight=delta,
                trade_weight=trade_weight,
                action=action,
            )
        )

    applied = False
    if request.apply and rebalance_required:
        # Apply writes target weights and triggers existing downstream allocation sync.
        update_portfolio_weights(request.portfolio_id, target_weights)
        applied = True

    plan = RebalancePlan(
        portfolio_id=request.portfolio_id,
        account=get_portfolio_account(request.portfolio_id),
        method=request.method,
        threshold=request.threshold,
        strategies=strategies,
        current_weights=current_weights,
        target_weights=target_weights,
        legs=legs,
        l1_drift=sum(abs_deltas),
        max_abs_drift=max(abs_deltas) if abs_deltas else 0.0,
        rebalance_required=rebalance_required,
        applied=applied,
        generated_at=_utc_now_iso(),
    )

    status = "applied" if applied else ("needs_rebalance" if rebalance_required else "noop")
    try:
        # Rebalance history is audit data; failures are logged but do not fail the API response.
        record_rebalance_run(
            portfolio_id=plan.portfolio_id,
            account=plan.account,
            method=plan.method.value,
            threshold=plan.threshold,
            strategies=plan.strategies,
            current_weights=plan.current_weights,
            target_weights=plan.target_weights,
            trade_weights=[leg.trade_weight for leg in plan.legs],
            status=status,
            meta={"apply_requested": request.apply},
            created_at=plan.generated_at,
        )
    except Exception:
        logger.exception("Failed to record rebalance run for portfolio_id=%s", request.portfolio_id)

    return plan
