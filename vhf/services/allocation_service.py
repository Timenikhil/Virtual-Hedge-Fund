from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from vhf.ai.weight_allocator_provider import (
    WeightAllocatorProviderError,
    resolve_allocator_provider,
)
from vhf.db.operations import (
    get_db_portfolio_id,
    get_db_strat,
    record_allocation_snapshot,
    update_portfolio_weights,
)
from vhf.logging.log import logger
from vhf.models.allocation import AllocationMethod, AllocationRequest, AllocationResult
from vhf.models.portfolio import Portfolio


class AllocationServiceError(ValueError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _equal_weights(n: int) -> list[float]:
    if n <= 0:
        raise AllocationServiceError("Cannot allocate a portfolio with zero strategies.")
    return [1.0 / n] * n


def _validate_weight_vector(weights: list[float], expected_len: int, label: str) -> list[float]:
    # Validate shape and numeric safety before any normalization/persistence.
    if len(weights) != expected_len:
        raise AllocationServiceError(
            f"{label} length mismatch: expected {expected_len}, got {len(weights)}."
        )

    validated: list[float] = []
    for idx, value in enumerate(weights):
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise AllocationServiceError(f"{label}[{idx}] is not a valid number: {value!r}") from exc

        if not math.isfinite(num):
            raise AllocationServiceError(f"{label}[{idx}] is not finite: {num!r}")
        if num < 0:
            raise AllocationServiceError(f"{label}[{idx}] is negative: {num!r}")

        validated.append(num)

    if sum(validated) <= 0:
        raise AllocationServiceError(f"{label} sum must be greater than 0.")

    return validated


def _normalize(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        raise AllocationServiceError("Cannot normalize weights with non-positive sum.")
    return [w / total for w in weights]


def _latest_strategy_score(strategy_id: str) -> float:
    """
    Score a strategy by its end-to-end price momentum.
    Returns a value > 0 so that strategies with no history still receive equal weight.
    Momentum is expressed as (end/start), floored at a small positive value.
    """
    strategy = get_db_strat(strategy_id)
    prices = [float(v) for v in strategy.prices if v is not None and math.isfinite(float(v))]
    if len(prices) < 2 or prices[0] <= 0:
        return 1.0  # neutral — participates with baseline weight
    momentum_ratio = prices[-1] / prices[0]
    return max(momentum_ratio, 0.01)  # floor at 1% to avoid zero/negative weights


def _build_strategy_context(strategy_id: str) -> dict[str, Any]:
    try:
        strategy = get_db_strat(strategy_id)
    except Exception:
        logger.exception("Failed to load strategy context for strategy_id=%s", strategy_id)
        return {"strategy_id": strategy_id, "prices": []}

    prices: list[float] = []
    for raw in strategy.prices:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            prices.append(value)

    return {
        "strategy_id": strategy.strategy_id,
        "name": strategy.name,
        "description": strategy.description,
        "category": strategy.category,
        "prices": prices,
        "latest_price": prices[-1] if prices else None,
        "price_count": len(prices),
    }


def _build_ai_context(portfolio: Portfolio, request: AllocationRequest) -> dict[str, Any]:
    strategy_ids = list(portfolio.strategies)

    current_weights: list[float] | None = None
    if portfolio.weights and len(portfolio.weights) == len(strategy_ids):
        try:
            current_weights = _normalize(_validate_weight_vector(portfolio.weights, len(strategy_ids), "portfolio.weights"))
        except AllocationServiceError:
            current_weights = None

    context: dict[str, Any] = {
        "portfolio_id": request.portfolio_id,
        "strategies": strategy_ids,
        "current_weights": current_weights,
        "strategy_data": [_build_strategy_context(strategy_id) for strategy_id in strategy_ids],
        "generated_at": _utc_now_iso(),
    }

    if request.ai_context is not None:
        # Keep partner integration flexible: caller can pass arbitrary feature payload.
        context["request_context"] = request.ai_context

    return context


def _extract_ai_weights(response: Any, strategies: list[str]) -> list[float]:
    expected_len = len(strategies)

    if isinstance(response, (list, tuple)):
        return _validate_weight_vector(list(response), expected_len, "ai_response")

    if not isinstance(response, dict):
        raise AllocationServiceError(
            "Unsupported AI provider response type. Expected list or dict."
        )

    for key in ("weights", "target_weights", "raw_weights"):
        values = response.get(key)
        if isinstance(values, (list, tuple)):
            return _validate_weight_vector(list(values), expected_len, f"ai_response.{key}")

    allocations = response.get("allocations")
    if isinstance(allocations, dict):
        values = [allocations.get(strategy_id) for strategy_id in strategies]
        return _validate_weight_vector(values, expected_len, "ai_response.allocations")

    if isinstance(allocations, list):
        mapped: dict[str, Any] = {}
        for row in allocations:
            if isinstance(row, dict) and "strategy_id" in row and "weight" in row:
                mapped[str(row["strategy_id"])] = row["weight"]
        if mapped:
            values = [mapped.get(strategy_id) for strategy_id in strategies]
            return _validate_weight_vector(values, expected_len, "ai_response.allocations")

    if all(strategy_id in response for strategy_id in strategies):
        values = [response.get(strategy_id) for strategy_id in strategies]
        return _validate_weight_vector(values, expected_len, "ai_response")

    raise AllocationServiceError(
        "AI provider response missing weights. Supported shapes: list, {'weights': [...]}, "
        "{'allocations': {'sid': weight}}, or {'sid': weight} map."
    )


def allocate_portfolio(request: AllocationRequest) -> AllocationResult:
    portfolio = get_db_portfolio_id(request.portfolio_id)
    strategies = portfolio.strategies
    if not strategies:
        raise AllocationServiceError("Portfolio has no strategies to allocate.")

    n = len(strategies)
    fallback_applied = False
    fallback_reason: str | None = None
    ai_provider_mode = None
    ai_provider_name: str | None = None
    ai_provider_error: str | None = None

    if request.method == AllocationMethod.equal_weight:
        # Deterministic baseline allocator.
        raw_weights = _equal_weights(n)

    elif request.method == AllocationMethod.score_weighted:
        # Dynamic allocator: convert per-strategy score into a raw weight vector.
        scores = [_latest_strategy_score(strategy_id) for strategy_id in strategies]
        if sum(scores) <= 0:
            fallback_applied = True
            fallback_reason = "score_weighted produced non-positive total score; used equal_weight fallback"
            raw_weights = _equal_weights(n)
        else:
            raw_weights = _validate_weight_vector(scores, n, "scores")

    elif request.method == AllocationMethod.ai_weighted:
        resolved_mode, provider = resolve_allocator_provider(request.ai_provider_mode)
        ai_provider_mode = resolved_mode
        ai_provider_name = getattr(provider, "name", None)

        try:
            ai_context = _build_ai_context(portfolio, request)
            provider_output = provider.allocate(ai_context, timeout_seconds=request.ai_timeout_seconds)
            raw_weights = _extract_ai_weights(provider_output, strategies)
        except (WeightAllocatorProviderError, AllocationServiceError) as exc:
            ai_provider_error = str(exc)
            if request.ai_strict:
                raise AllocationServiceError(
                    f"ai_weighted allocation failed in strict mode: {exc}"
                ) from exc

            fallback_applied = True
            fallback_reason = "ai_weighted provider failed; used equal_weight fallback"
            raw_weights = _equal_weights(n)
        except Exception as exc:
            ai_provider_error = str(exc)
            if request.ai_strict:
                raise AllocationServiceError(
                    f"ai_weighted allocation failed in strict mode: {exc}"
                ) from exc

            fallback_applied = True
            fallback_reason = "ai_weighted provider failed; used equal_weight fallback"
            raw_weights = _equal_weights(n)

    else:
        # Manual mode can come from request payload or previously stored portfolio weights.
        source_weights = request.raw_weights if request.raw_weights is not None else portfolio.weights
        if not source_weights:
            fallback_applied = True
            fallback_reason = "manual weights missing; used equal_weight fallback"
            raw_weights = _equal_weights(n)
        else:
            raw_weights = _validate_weight_vector(source_weights, n, "raw_weights")

    target_weights = _normalize(raw_weights)

    persisted = False
    if request.persist:
        # Persisting here also reuses existing allocation-sync behavior in DB operations.
        update_portfolio_weights(request.portfolio_id, target_weights)
        persisted = True

    result = AllocationResult(
        portfolio_id=request.portfolio_id,
        method=request.method,
        strategies=strategies,
        raw_weights=[float(v) for v in raw_weights],
        target_weights=target_weights,
        fallback_applied=fallback_applied,
        fallback_reason=fallback_reason,
        persisted=persisted,
        ai_provider_mode=ai_provider_mode,
        ai_provider_name=ai_provider_name,
        ai_provider_error=ai_provider_error,
        generated_at=_utc_now_iso(),
    )

    try:
        # Snapshot writes are best-effort: allocation responses should still succeed.
        record_allocation_snapshot(
            portfolio_id=result.portfolio_id,
            method=result.method.value,
            strategies=result.strategies,
            raw_weights=result.raw_weights,
            target_weights=result.target_weights,
            meta={
                "fallback_applied": result.fallback_applied,
                "fallback_reason": result.fallback_reason,
                "persisted": result.persisted,
                "ai_provider_mode": result.ai_provider_mode.value if result.ai_provider_mode else None,
                "ai_provider_name": result.ai_provider_name,
                "ai_provider_error": result.ai_provider_error,
            },
            created_at=result.generated_at,
        )
    except Exception:
        logger.exception("Failed to record allocation snapshot for portfolio_id=%s", request.portfolio_id)

    return result
