from enum import Enum
from typing import Any, List

from pydantic import BaseModel, Field


class AllocationMethod(str, Enum):
    """Supported allocation policies."""
    manual = "manual"
    equal_weight = "equal_weight"
    score_weighted = "score_weighted"
    ai_weighted = "ai_weighted"


class AIProviderMode(str, Enum):
    """Where AI portfolio weights are sourced from."""

    auto = "auto"
    local = "local"
    remote = "remote"
    disabled = "disabled"


DEFAULT_AI_TIMEOUT_SECONDS = 30.0


class AllocationRequest(BaseModel):
    """Request payload for computing target portfolio weights."""
    portfolio_id: int
    method: AllocationMethod = AllocationMethod.manual
    # Optional manual vector. Used when `method=manual`.
    raw_weights: List[float] | None = None
    # Optional provider override for `method=ai_weighted`.
    ai_provider_mode: AIProviderMode | None = None
    # For `method=ai_weighted`: fail hard on provider error instead of fallback.
    ai_strict: bool = False
    # Max parse/validation retries before fallback (0 = no retries, max 2).
    ai_max_retries: int = Field(default=1, ge=0, le=2)
    # Timeout override for remote/local provider execution.
    ai_timeout_seconds: float = Field(default=DEFAULT_AI_TIMEOUT_SECONDS, gt=0.0)
    # Optional caller-supplied context merged into AI payload.
    ai_context: dict[str, Any] | None = None
    # If true, write normalized target weights back to the portfolio record.
    persist: bool = False


class AllocationResult(BaseModel):
    """Allocation output with both pre-normalization and normalized vectors."""
    portfolio_id: int
    method: AllocationMethod
    strategies: List[str]
    raw_weights: List[float]
    target_weights: List[float]
    fallback_applied: bool = False
    fallback_reason: str | None = None
    persisted: bool = False
    ai_provider_mode: AIProviderMode | None = None
    ai_provider_name: str | None = None
    ai_provider_error: str | None = None
    ai_retry_count: int = 0
    generated_at: str = Field(description="UTC ISO timestamp")
