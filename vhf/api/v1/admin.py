from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query, Security
from pydantic import BaseModel
from typing import Dict, Optional, List

from requests import HTTPError

from vhf.authentication.authentication import check_role
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
from vhf.models.user import UserRole

router = APIRouter(
                       prefix="/admin",
                       tags=["admin"],
                       responses={
                           400: {
                               "model": HTTPError,
                               "description": "Invalid request."
                           }
                       },
    dependencies=[Security(check_role([UserRole.ADMIN, UserRole.CFL]))]
)


class TradeRequest(BaseModel):
    strategy: str
    review_date: Optional[str] = "latest"  # or an ISO date
    accounts: Optional[List[str]] = None
    dry_run: bool = False


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
