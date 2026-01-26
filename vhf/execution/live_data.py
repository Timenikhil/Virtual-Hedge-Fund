from __future__ import annotations
from typing import Iterable, Mapping

from vhf.quantrocket.cli import (
    QuantRocketCliError,
    realtime_collect,
    realtime_create_agg_db,
    realtime_create_tick_db,
    realtime_db,
    realtime_list,
    realtime_stop,
)


class RealtimeError(RuntimeError):
    pass


def create_tick_db(
    code: str,
    *,
    vendor: str,  # "alpaca" | "polygon" | "ibkr"
    universes: Iterable[str] | None = None,
    sids: Iterable[str] | None = None,
    fields: Iterable[str] | None = None,  # e.g. ["Last","LastSize","Bid","Ask"]
    primary_exchange: bool | None = None,  # IBKR-only
) -> dict:
    try:
        return realtime_create_tick_db(
            code,
            vendor=vendor,
            universes=universes,
            sids=sids,
            fields=fields,
            primary_exchange=primary_exchange,
        )
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc


def create_agg_db(
    parent_code: str,
    agg_code: str,
    *,
    bar_size: str = "1m",
    field_map: Mapping[str, Iterable[str]] | None = None,
) -> dict:
    """
    field_map example:
      {"Last": ["Open","High","Low","Close"], "LastSize":["Sum"]}
    """
    try:
        return realtime_create_agg_db(
            parent_code,
            agg_code,
            bar_size=bar_size,
            field_map=field_map,
        )
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc


def start_collection(*codes: str, wait: bool = False, until: str | None = None) -> dict:
    """
    Start streaming collection for one or more tick DBs.
    until: optional ISO like '2025-10-30T20:00:00Z'
    """
    try:
        return realtime_collect(codes, wait=wait, until=until)
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc


def stop_collection(*codes: str) -> dict:
    try:
        return realtime_stop(codes)
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc


def list_dbs() -> dict:
    try:
        return realtime_list()
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc


def get_db(code: str) -> dict:
    try:
        return realtime_db(code)
    except QuantRocketCliError as exc:
        raise RealtimeError(str(exc)) from exc
