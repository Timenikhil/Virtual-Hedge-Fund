from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from vhf.db.operations import (
    bulk_upsert_strategies,
    create_reconcile_job,
    delete_portfolio,
    delete_reconcile_job,
    delete_strategy,
    get_allocation_history,
    get_rebalance_history,
    get_reconcile_job,
    list_reconcile_jobs,
    record_strategy_price_points,
    set_reconcile_job_enabled,
    update_portfolio,
    update_reconcile_job,
    upsert_strategy,
)
from vhf.execution.alpaca_trade_api import (
    QuantRocketError,
    generate_orders_csv,
    trade_strategy_to_alpaca,
)
from vhf.execution.live_data import (
    RealtimeError,
    create_agg_db,
    create_tick_db,
    get_db,
    list_dbs,
    start_collection,
    stop_collection,
)
from vhf.models.allocation import AIProviderMode, AllocationMethod
from vhf.models.portfolio import Portfolio
from vhf.models.reconcile import (
    ReconcileJob,
    ReconcileJobCreateRequest,
    ReconcileJobEnabledRequest,
    ReconcileRunResult,
)
from vhf.models.strategy import Strategy, StrategyPrice
from vhf.services.backtest import BacktestError, BacktestRequest, BacktestResult, run_backtest
from vhf.services.reconcile_scheduler import SCHEDULER_ENABLED, scheduler
from vhf.services.reconcile_service import ReconcileServiceError, run_reconcile_job

router = APIRouter()


# ---------------------------------------------------------------------------
# Reconcile jobs
# ---------------------------------------------------------------------------

@router.post("/reconcile/jobs", response_model=ReconcileJob)
def api_create_reconcile_job(req: ReconcileJobCreateRequest):
    """Create a recurring reconcile job."""
    if req.interval_seconds <= 0:
        raise HTTPException(status_code=400, detail="interval_seconds must be > 0")
    if req.threshold < 0:
        raise HTTPException(status_code=400, detail="threshold must be >= 0")

    return create_reconcile_job(
        portfolio_id=req.portfolio_id,
        interval_seconds=req.interval_seconds,
        method=req.method,
        threshold=req.threshold,
        apply=req.apply,
        execute_trades=req.execute_trades,
        dry_run_trades=req.dry_run_trades,
        review_date=req.review_date,
        ai_provider_mode=req.ai_provider_mode,
        ai_strict=req.ai_strict,
        ai_timeout_seconds=req.ai_timeout_seconds,
        ai_context=req.ai_context,
        enabled=req.enabled,
    )


@router.get("/reconcile/jobs", response_model=List[ReconcileJob])
def api_list_reconcile_jobs():
    """List all reconcile jobs."""
    return list_reconcile_jobs()


@router.get("/reconcile/jobs/{job_id}", response_model=ReconcileJob)
def api_get_reconcile_job(job_id: int):
    """Get one reconcile job by id."""
    return get_reconcile_job(job_id)


class ReconcileJobUpdateRequest(BaseModel):
    """Partial update for a reconcile job. Only supplied fields are changed."""
    interval_seconds: Optional[int] = None
    method: Optional[AllocationMethod] = None
    threshold: Optional[float] = None
    apply: Optional[bool] = None
    execute_trades: Optional[bool] = None
    dry_run_trades: Optional[bool] = None
    review_date: Optional[str] = None
    ai_provider_mode: Optional[AIProviderMode] = None
    ai_strict: Optional[bool] = None
    ai_timeout_seconds: Optional[float] = None
    ai_context: Optional[Dict[str, Any]] = None


@router.patch("/reconcile/jobs/{job_id}", response_model=ReconcileJob)
def api_update_reconcile_job(job_id: int, req: ReconcileJobUpdateRequest):
    """Partially update a reconcile job's configuration."""
    return update_reconcile_job(
        job_id,
        interval_seconds=req.interval_seconds,
        method=req.method,
        threshold=req.threshold,
        apply=req.apply,
        execute_trades=req.execute_trades,
        dry_run_trades=req.dry_run_trades,
        review_date=req.review_date,
        ai_provider_mode=req.ai_provider_mode,
        ai_strict=req.ai_strict,
        ai_timeout_seconds=req.ai_timeout_seconds,
        ai_context=req.ai_context,
    )


@router.delete("/reconcile/jobs/{job_id}", status_code=204)
def api_delete_reconcile_job(job_id: int):
    """Permanently delete a reconcile job."""
    delete_reconcile_job(job_id)


@router.post("/reconcile/jobs/{job_id}/enabled", response_model=ReconcileJob)
def api_set_reconcile_job_enabled(job_id: int, req: ReconcileJobEnabledRequest):
    """Enable or disable a reconcile job."""
    return set_reconcile_job_enabled(job_id, req.enabled)


@router.post("/reconcile/jobs/{job_id}/run", response_model=ReconcileRunResult)
def api_run_reconcile_job(job_id: int):
    """Execute a reconcile job immediately."""
    try:
        return run_reconcile_job(job_id)
    except ReconcileServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reconcile/scheduler/run-due", response_model=List[ReconcileRunResult])
async def api_run_due_reconcile_jobs_once():
    """Trigger a one-off pass over all due jobs."""
    return await scheduler.run_due_jobs_once()


@router.post("/reconcile/scheduler/start")
async def api_start_reconcile_scheduler():
    """Start the in-process scheduler loop."""
    await scheduler.start()
    return {"enabled": SCHEDULER_ENABLED, "running": scheduler.is_running}


@router.post("/reconcile/scheduler/stop")
async def api_stop_reconcile_scheduler():
    """Stop the in-process scheduler loop."""
    await scheduler.stop()
    return {"enabled": SCHEDULER_ENABLED, "running": scheduler.is_running}


@router.get("/reconcile/scheduler/status")
def api_reconcile_scheduler_status():
    """Return scheduler configuration and current runtime status."""
    next_poll = scheduler.next_poll_at
    return {
        "enabled_by_config": SCHEDULER_ENABLED,
        "running": scheduler.is_running,
        "poll_interval_seconds": scheduler.poll_interval_seconds,
        "next_poll_at": next_poll.isoformat() if next_poll else None,
    }


# ---------------------------------------------------------------------------
# Trade execution
# ---------------------------------------------------------------------------

class TradeRequest(BaseModel):
    strategy: str
    review_date: Optional[str] = "latest"
    accounts: Optional[List[str]] = None
    dry_run: bool = False


@router.post("/trade")
def trade(req: TradeRequest):
    """
    Execute a one-shot Moonshot trade for a strategy.
    dry_run=true returns CSV orders without submitting them.
    """
    try:
        if req.dry_run:
            csv_text = generate_orders_csv(req.strategy, req.review_date, req.accounts)
            return {"status": "dry_run", "csv": csv_text}
        result = trade_strategy_to_alpaca(req.strategy, req.review_date, req.accounts)
        return result
    except QuantRocketError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders.csv")
def preview_orders(strategy: str = Query(...), review_date: str = Query("latest")):
    """Retrieve CSV orders for quick inspection (no submission)."""
    try:
        return generate_orders_csv(strategy, review_date)
    except QuantRocketError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------------------------------------------------------------------------
# Realtime data
# ---------------------------------------------------------------------------

class CreateTickDBReq(BaseModel):
    code: str
    vendor: str
    universes: Optional[List[str]] = None
    sids: Optional[List[str]] = None
    fields: Optional[List[str]] = ["Last", "LastSize"]
    primary_exchange: Optional[bool] = None


@router.post("/realtime/create-tick-db")
def api_create_tick_db(req: CreateTickDBReq):
    try:
        return create_tick_db(
            req.code,
            vendor=req.vendor,
            universes=req.universes,
            sids=req.sids,
            fields=req.fields,
            primary_exchange=req.primary_exchange,
        )
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class CreateAggDBReq(BaseModel):
    parent_code: str
    agg_code: str
    bar_size: str = "1m"
    field_map: Dict[str, List[str]] = {
        "Last": ["Open", "High", "Low", "Close"],
        "LastSize": ["Sum"],
    }


@router.post("/realtime/create-agg-db")
def api_create_agg_db(req: CreateAggDBReq):
    try:
        return create_agg_db(
            req.parent_code,
            req.agg_code,
            bar_size=req.bar_size,
            field_map=req.field_map,
        )
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class StartCollectReq(BaseModel):
    codes: List[str]
    wait: bool = False
    until: Optional[str] = None


@router.post("/realtime/start")
def api_start_collect(req: StartCollectReq):
    try:
        return start_collection(*req.codes, wait=req.wait, until=req.until)
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class StopCollectReq(BaseModel):
    codes: List[str]


@router.post("/realtime/stop")
def api_stop_collect(req: StopCollectReq):
    try:
        return stop_collection(*req.codes)
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/realtime/dbs")
def api_list_dbs():
    try:
        return list_dbs()
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/realtime/db/{code}")
def api_get_db(code: str):
    try:
        return get_db(code)
    except RealtimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ---------------------------------------------------------------------------
# Strategy management
# ---------------------------------------------------------------------------

class StrategyUpsertRequest(BaseModel):
    strategy_id: str
    name: str
    description: str = ""
    category: str = ""


class StrategyPricePointsRequest(BaseModel):
    """List of (ISO timestamp, price) pairs to record for a strategy."""
    points: List[Tuple[str, float]] = Field(default_factory=list)


@router.get("/strategies/{strategy_id}", response_model=StrategyPrice)
def api_get_strategy(strategy_id: str):
    """Retrieve a single strategy by ID, including its price history."""
    from vhf.db.operations import get_db_strat
    return get_db_strat(strategy_id)


@router.post("/strategies", response_model=Strategy)
def api_upsert_strategy(req: StrategyUpsertRequest):
    """Create or update a single strategy record."""
    if not req.strategy_id.strip():
        raise HTTPException(status_code=400, detail="strategy_id must be non-empty")
    return upsert_strategy(
        strategy_id=req.strategy_id.strip(),
        name=req.name,
        description=req.description,
        category=req.category,
    )


@router.post("/strategies/bulk", response_model=List[Strategy])
def api_bulk_upsert_strategies(strategies: List[StrategyUpsertRequest]):
    """Create or update multiple strategy records in a single transaction."""
    if not strategies:
        raise HTTPException(status_code=400, detail="strategies list must not be empty")
    return bulk_upsert_strategies([s.model_dump() for s in strategies])


@router.post("/strategies/sync-qr")
def api_sync_qr_strategies(codeload_path: str | None = None) -> dict:
    """
    Scan the QuantRocket codeload volume for Moonshot strategy .py files and
    upsert any discovered strategies into the database with source='quantrocket'.

    Pass codeload_path to override the default CODELOAD_PATH env var / /codeload.
    Returns a summary of how many strategies were found and upserted.
    """
    from vhf.quantrocket.strategy_scanner import scan_codeload
    discovered = scan_codeload(codeload_path)
    if not discovered:
        return {"found": 0, "upserted": 0, "strategies": []}
    bulk_upsert_strategies(discovered)
    return {
        "found": len(discovered),
        "upserted": len(discovered),
        "strategies": [s["strategy_id"] for s in discovered],
    }


@router.delete("/strategies/{strategy_id}", status_code=204)
def api_delete_strategy(strategy_id: str):
    """Delete a strategy and all its price history."""
    delete_strategy(strategy_id)


@router.post("/strategies/{strategy_id}/prices", status_code=204)
def api_record_strategy_prices(strategy_id: str, req: StrategyPricePointsRequest):
    """Append or upsert historical price points for a strategy."""
    if not req.points:
        raise HTTPException(status_code=400, detail="points list must not be empty")
    record_strategy_price_points(strategy_id, req.points)


class SyncBacktestRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# In-memory job store: job_id → {status, strategy_id, points_stored?, detail?}
_backtest_jobs: Dict[str, Dict] = {}


def _run_backtest_job(job_id: str, strategy_id: str, start_date: Optional[str], end_date: Optional[str]) -> None:
    from vhf.quantrocket.backtest_sync import BacktestSyncError, sync_strategy_backtest
    try:
        n = sync_strategy_backtest(strategy_id, start_date=start_date, end_date=end_date)
        _backtest_jobs[job_id] = {"status": "done", "strategy_id": strategy_id, "points_stored": n}
    except BacktestSyncError as exc:
        _backtest_jobs[job_id] = {"status": "error", "strategy_id": strategy_id, "detail": str(exc)}
    except Exception as exc:
        _backtest_jobs[job_id] = {"status": "error", "strategy_id": strategy_id, "detail": f"Unexpected error: {exc}"}


@router.post("/strategies/{strategy_id}/sync-backtest", status_code=202)
def api_sync_strategy_backtest(strategy_id: str, req: SyncBacktestRequest, background_tasks: BackgroundTasks):
    """
    Start a QR Moonshot backtest for a strategy in the background.
    Returns a job_id immediately. Poll GET /strategies/{id}/sync-backtest/{job_id} for status.
    """
    job_id = uuid.uuid4().hex[:12]
    _backtest_jobs[job_id] = {"status": "running", "strategy_id": strategy_id}
    background_tasks.add_task(_run_backtest_job, job_id, strategy_id, req.start_date, req.end_date)
    return {"job_id": job_id, "status": "running"}


@router.get("/strategies/{strategy_id}/sync-backtest/{job_id}")
def api_get_backtest_job(strategy_id: str, job_id: str):
    """Poll backtest job status."""
    job = _backtest_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Portfolio management
# ---------------------------------------------------------------------------

class PortfolioUpdateRequest(BaseModel):
    portfolio_name: Optional[str] = None
    account: Optional[str] = None


@router.patch("/portfolios/{portfolio_id}", response_model=Portfolio)
def api_update_portfolio(portfolio_id: int, req: PortfolioUpdateRequest):
    """Update a portfolio's name and/or account mapping."""
    if req.portfolio_name is None and req.account is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")
    return update_portfolio(portfolio_id, portfolio_name=req.portfolio_name, account=req.account)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
def api_delete_portfolio(portfolio_id: int):
    """Permanently delete a portfolio and all its associated data."""
    delete_portfolio(portfolio_id)


# ---------------------------------------------------------------------------
# Audit history
# ---------------------------------------------------------------------------

@router.get("/portfolios/{portfolio_id}/allocation-history")
def api_allocation_history(
    portfolio_id: int,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent allocation snapshots for a portfolio, newest first."""
    return get_allocation_history(portfolio_id, limit=limit)


@router.get("/portfolios/{portfolio_id}/rebalance-history")
def api_rebalance_history(
    portfolio_id: int,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent rebalance runs for a portfolio, newest first."""
    return get_rebalance_history(portfolio_id, limit=limit)


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------

@router.post("/backtest", response_model=BacktestResult)
def api_backtest(request: BacktestRequest):
    """
    Run a historical backtest for a portfolio using stored price data.

    Supports equal_weight, score_weighted (momentum), and manual allocation methods.
    ai_weighted falls back to score_weighted during backtesting to avoid
    calling Claude once per rebalance date.

    Returns performance metrics (total return, annualised return, Sharpe ratio,
    max drawdown) and a daily portfolio value series.
    """
    try:
        return run_backtest(request)
    except BacktestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
