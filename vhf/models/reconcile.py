from datetime import datetime
from typing import Any, List

from pydantic import BaseModel, Field

from vhf.models.allocation import AllocationMethod

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
DEFAULT_RECONCILE_INTERVAL_SECONDS = SECONDS_PER_DAY
DEFAULT_REBALANCE_THRESHOLD = 0.02


class ReconcileJobCreateRequest(BaseModel):
    """Create a recurring reconcile job for a portfolio."""

    portfolio_id: int
    interval_seconds: int = Field(default=DEFAULT_RECONCILE_INTERVAL_SECONDS, gt=0)
    method: AllocationMethod = AllocationMethod.manual
    threshold: float = Field(default=DEFAULT_REBALANCE_THRESHOLD, ge=0.0)
    apply: bool = True
    execute_trades: bool = False
    dry_run_trades: bool = True
    review_date: str | None = "latest"
    enabled: bool = True


class ReconcileJobEnabledRequest(BaseModel):
    """Toggle a reconcile job on/off."""

    enabled: bool


class ReconcileJob(BaseModel):
    """Persisted reconcile scheduler configuration and run state."""

    job_id: int
    portfolio_id: int
    interval_seconds: int
    method: AllocationMethod
    threshold: float
    apply: bool
    execute_trades: bool
    dry_run_trades: bool
    review_date: str | None
    enabled: bool
    created_at: str
    updated_at: str
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class StrategyTradeResult(BaseModel):
    """Execution output for a single strategy trade command."""

    strategy_id: str
    mode: str
    status: str
    detail: Any = None


class ReconcileRunResult(BaseModel):
    """End-to-end result for one reconcile cycle."""

    job_id: int
    portfolio_id: int
    status: str
    plan_status: str
    rebalance_required: bool
    applied: bool
    trades_executed: bool
    trade_results: List[StrategyTradeResult] = Field(default_factory=list)
    generated_at: str
