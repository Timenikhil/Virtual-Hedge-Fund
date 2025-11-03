from __future__ import annotations
import os
import requests
from typing import Iterable, Mapping

DEFAULT_HOUSTON = "http://localhost:1969"
HOUSTON = os.getenv("HOUSTON_URL", DEFAULT_HOUSTON)


class RealtimeError(RuntimeError):
    pass


def _req(method: str, path: str, **kw) -> requests.Response:
    url = f"{HOUSTON}{path}"
    try:
        r = requests.request(method, url, timeout=60, **kw)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        raise RealtimeError(f"{method} {url} failed: {e}") from e


def create_tick_db(
    code: str,
    *,
    vendor: str,  # "alpaca" | "polygon" | "ibkr"
    universes: Iterable[str] | None = None,
    sids: Iterable[str] | None = None,
    fields: Iterable[str] | None = None,  # e.g. ["Last","LastSize","Bid","Ask"]
    primary_exchange: bool | None = None,  # IBKR-only
) -> dict:
    params: dict[str, str] = {"vendor": vendor}
    if universes:
        params["universes"] = ",".join(universes)
    if sids:
        params["sids"] = ",".join(sids)
    if fields:
        # repeat fields= param
        # requests will encode as fields=...&fields=...
        # pass via 'params' with list values
        pass
    if primary_exchange is not None:
        params["primary_exchange"] = "true" if primary_exchange else "false"

    # build params with repeated fields
    qp = []
    for k, v in params.items():
        if k != "fields":
            qp.append((k, v))
    if fields:
        for f in fields:
            qp.append(("fields", f))

    r = _req("PUT", f"/realtime/databases/{code}", params=qp)
    try:
        return r.json()
    except ValueError:
        return {"result": r.text}


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
    qp: list[tuple[str, str]] = [("bar_size", bar_size)]
    if field_map:
        for src, aggs in field_map.items():
            qp.append(("fields", f"{src}:{','.join(aggs)}"))
    r = _req(
        "PUT", f"/realtime/databases/{parent_code}/aggregates/{agg_code}", params=qp
    )
    try:
        return r.json()
    except ValueError:
        return {"result": r.text}


def start_collection(*codes: str, wait: bool = False, until: str | None = None) -> dict:
    """
    Start streaming collection for one or more tick DBs.
    until: optional ISO like '2025-10-30T20:00:00Z'
    """
    params: list[tuple[str, str]] = [("codes", ",".join(codes))]
    params.append(("wait", "true" if wait else "false"))
    if until:
        params.append(("until", until))
    r = _req("POST", "/realtime/collections", params=params)
    try:
        return r.json()
    except ValueError:
        return {"result": r.text}


def stop_collection(*codes: str) -> dict:
    r = _req("DELETE", "/realtime/collections", params=[("codes", ",".join(codes))])
    try:
        return r.json()
    except ValueError:
        return {"result": r.text}


def list_dbs() -> dict:
    return _req("GET", "/realtime/databases").json()


def get_db(code: str) -> dict:
    return _req("GET", f"/realtime/databases/{code}").json()
