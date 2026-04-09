from typing import Any, List

from pydantic import BaseModel, Field

from vhf.models.allocation import (
    AIProviderMode,
    AllocationMethod,
    DEFAULT_AI_TIMEOUT_SECONDS,
)

DEFAULT_REBALANCE_THRESHOLD = 0.02


class RebalanceRequest(BaseModel):
    """Input payload for building (and optionally applying) a rebalance plan."""

    portfolio_id: int
    method: AllocationMethod = AllocationMethod.manual
    # Optional manual weights passed through to allocation step for `method=manual`.
    allocation_raw_weights: List[float] | None = None
    # Optional current live book weights; falls back to stored portfolio weights if omitted.
    current_weights: List[float] | None = None
    # Optional AI-provider override when `method=ai_weighted`.
    ai_provider_mode: AIProviderMode | None = None
    # If true, AI allocation errors fail the request instead of using a fallback.
    ai_strict: bool = False
    # Timeout override for remote/local AI allocation execution.
    ai_timeout_seconds: float = Field(default=DEFAULT_AI_TIMEOUT_SECONDS, gt=0.0)
    # Optional context payload forwarded to the AI allocator.
    ai_context: dict[str, Any] | None = None
    # Minimum absolute drift required before a trade leg is emitted.
    threshold: float = DEFAULT_REBALANCE_THRESHOLD
    # If true, apply target weights to the portfolio after plan generation.
    apply: bool = False


class RebalanceLeg(BaseModel):
    """Per-strategy rebalance instruction in weight-space."""

    strategy_id: str
    current_weight: float
    target_weight: float
    delta_weight: float
    trade_weight: float
    action: str


class RebalancePlan(BaseModel):
    """Computed rebalance plan with drift diagnostics and optional apply status."""

    portfolio_id: int
    account: str | None = None
    method: AllocationMethod
    threshold: float
    strategies: List[str]
    current_weights: List[float]
    target_weights: List[float]
    legs: List[RebalanceLeg]
    l1_drift: float
    max_abs_drift: float
    rebalance_required: bool
    applied: bool = False
    generated_at: str = Field(description="UTC ISO timestamp")
