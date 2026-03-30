from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List, Tuple
from vhf.db.operations import (
    bulk_upsert_strategies,
    create_reconcile_job,
    delete_strategy,
    get_reconcile_job,
    list_reconcile_jobs,
    record_strategy_price_points,
    set_reconcile_job_enabled,
    upsert_strategy,
)
from vhf.models.strategy import Strategy
from vhf.execution.alpaca_trade_api import (
    trade_strategy_to_alpaca,
    generate_orders_csv,
    QuantRocketError,
)

from vhf.execution.live_data import (
    create_tick_db,
    create_agg_db,
    start_collection,
    stop_collection,
    list_dbs,
    get_db,
    RealtimeError,
)
from vhf.models.reconcile import (
    ReconcileJob,
    ReconcileJobCreateRequest,
    ReconcileJobEnabledRequest,
    ReconcileRunResult,
)
from vhf.services.reconcile_scheduler import SCHEDULER_ENABLED, scheduler
from vhf.services.reconcile_service import ReconcileServiceError, run_reconcile_job


router = APIRouter()


class TradeRequest(BaseModel):
    strategy: str
    review_date: Optional[str] = "latest"  # or an ISO date
    accounts: Optional[List[str]] = None
    dry_run: bool = False


@router.post("/reconcile/jobs", response_model=ReconcileJob)
def api_create_reconcile_job(req: ReconcileJobCreateRequest):
    """
    Create a recurring reconcile job.
    """
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
    """
    List all reconcile jobs.
    """
    return list_reconcile_jobs()


@router.get("/reconcile/jobs/{job_id}", response_model=ReconcileJob)
def api_get_reconcile_job(job_id: int):
    """
    Get one reconcile job by id.
    """
    return get_reconcile_job(job_id)


@router.post("/reconcile/jobs/{job_id}/enabled", response_model=ReconcileJob)
def api_set_reconcile_job_enabled(job_id: int, req: ReconcileJobEnabledRequest):
    """
    Enable or disable a reconcile job.
    """
    return set_reconcile_job_enabled(job_id, req.enabled)


@router.post("/reconcile/jobs/{job_id}/run", response_model=ReconcileRunResult)
def api_run_reconcile_job(job_id: int):
    """
    Execute a reconcile job immediately.
    """
    try:
        return run_reconcile_job(job_id)
    except ReconcileServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reconcile/scheduler/run-due", response_model=List[ReconcileRunResult])
async def api_run_due_reconcile_jobs_once():
    """
    Trigger a one-off pass over all due jobs.
    """
    return await scheduler.run_due_jobs_once()


@router.post("/reconcile/scheduler/start")
async def api_start_reconcile_scheduler():
    """
    Start the in-process scheduler loop.
    """
    await scheduler.start()
    return {"enabled": SCHEDULER_ENABLED, "running": scheduler.is_running}


@router.post("/reconcile/scheduler/stop")
async def api_stop_reconcile_scheduler():
    """
    Stop the in-process scheduler loop.
    """
    await scheduler.stop()
    return {"enabled": SCHEDULER_ENABLED, "running": scheduler.is_running}


@router.get("/reconcile/scheduler/status")
def api_reconcile_scheduler_status():
    """
    Return scheduler configuration and current runtime status.
    """
    return {
        "enabled_by_config": SCHEDULER_ENABLED,
        "running": scheduler.is_running,
        "poll_interval_seconds": scheduler.poll_interval_seconds,
    }


@router.post("/trade")
def trade(req: TradeRequest):
    """
    Execute a one-shot Moonshot trade for a strategy.
    - dry_run: returns CSV orders but does NOT submit them
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
    """
    Convenience GET: retrieve CSV orders for quick inspection (no submission).
    """
    try:
        csv_text = generate_orders_csv(strategy, review_date)
        return (
            csv_text  # FastAPI will return as text/plain; that’s fine for quick checks
        )
    except QuantRocketError as e:
        raise HTTPException(status_code=502, detail=str(e))


class CreateTickDBReq(BaseModel):
    code: str
    vendor: str  # "alpaca" | "polygon" | "ibkr"
    universes: Optional[List[str]] = None
    sids: Optional[List[str]] = None
    fields: Optional[List[str]] = ["Last", "LastSize"]
    primary_exchange: Optional[bool] = None  # IBKR-only


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


@router.post("/strategies", response_model=Strategy)
def api_upsert_strategy(req: StrategyUpsertRequest):
    """
    Create or update a single strategy record.
    """
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
    """
    Create or update multiple strategy records in a single transaction.
    """
    if not strategies:
        raise HTTPException(status_code=400, detail="strategies list must not be empty")
    return bulk_upsert_strategies([s.model_dump() for s in strategies])


@router.delete("/strategies/{strategy_id}", status_code=204)
def api_delete_strategy(strategy_id: str):
    """
    Delete a strategy and all its price history.
    """
    delete_strategy(strategy_id)


@router.post("/strategies/{strategy_id}/prices", status_code=204)
def api_record_strategy_prices(strategy_id: str, req: StrategyPricePointsRequest):
    """
    Append or upsert historical price points for a strategy.
    Each point is a [ISO-timestamp, price] pair.
    """
    if not req.points:
        raise HTTPException(status_code=400, detail="points list must not be empty")
    record_strategy_price_points(strategy_id, req.points)
