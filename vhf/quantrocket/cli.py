import os
import subprocess
from typing import Iterable
import json

# Defaults can be overridden via env vars.
COMPOSE_DIR = os.getenv("QUANTROCKET_COMPOSE_DIR", ".")
COMPOSE_FILE = os.getenv("QUANTROCKET_COMPOSE_FILE", "docker-compose.quantrocket.yml")
MOONSHOT_SERVICE = os.getenv("QUANTROCKET_MOONSHOT_SERVICE", "moonshot")


class QuantRocketCliError(RuntimeError):
    pass


def _run_compose_exec(args: Iterable[str], *, timeout: int = 600) -> str:
    """
    Execute a command inside the QuantRocket moonshot container via docker compose.
    Returns stdout, raises on non-zero exit.
    """
    compose_path = os.path.join(COMPOSE_DIR, COMPOSE_FILE)
    cmd = ["docker", "compose", "-f", compose_path, "exec", "-T", MOONSHOT_SERVICE]
    cmd.extend(args)
    try:
        proc = subprocess.run(
            cmd,
            cwd=COMPOSE_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.SubprocessError as exc:
        raise QuantRocketCliError(f"Failed to invoke QuantRocket CLI: {exc}") from exc

    if proc.returncode != 0:
        raise QuantRocketCliError(
            f"QuantRocket CLI failed (exit {proc.returncode}): {proc.stderr or proc.stdout}"
        )
    return proc.stdout


def _run_json(args: Iterable[str]) -> dict:
    out = _run_compose_exec(args)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise QuantRocketCliError(f"Unexpected non-JSON output: {out}") from exc


def moonshot_orders(
    strategy: str, *, review_date: str | None = None, accounts: list[str] | None = None
) -> str:
    """
    Run `quantrocket moonshot orders` for a strategy and return CSV output.
    """
    args = ["quantrocket", "moonshot", "orders", "--strategies", strategy]
    if review_date:
        args.extend(["--review-date", review_date])
    if accounts:
        args.extend(["--accounts", ",".join(accounts)])
    return _run_compose_exec(args)


def moonshot_trade(
    strategy: str, *, review_date: str | None = None, accounts: list[str] | None = None
) -> str:
    """
    Run `quantrocket moonshot trade` for a strategy and return CLI output.
    """
    args = ["quantrocket", "moonshot", "trade", strategy]
    if review_date:
        args.extend(["--review-date", review_date])
    if accounts:
        args.extend(["--accounts", ",".join(accounts)])
    return _run_compose_exec(args)


def realtime_create_tick_db(
    code: str,
    *,
    vendor: str,
    universes: Iterable[str] | None = None,
    sids: Iterable[str] | None = None,
    fields: Iterable[str] | None = None,
    primary_exchange: bool | None = None,
) -> dict:
    args: list[str] = ["quantrocket", "realtime", "create-tick-db", "-d", code, "-v", vendor, "-o", "json"]
    if universes:
        args.extend(["-u", ",".join(universes)])
    if sids:
        args.extend(["-s", ",".join(sids)])
    if fields:
        for f in fields:
            args.extend(["-f", f])
    if primary_exchange:
        args.append("--primary-exchange")
    return _run_json(args)


def realtime_create_agg_db(
    parent_code: str,
    agg_code: str,
    *,
    bar_size: str = "1m",
    field_map: dict[str, Iterable[str]] | None = None,
) -> dict:
    args: list[str] = [
        "quantrocket",
        "realtime",
        "create-agg-db",
        "-d",
        parent_code,
        "-a",
        agg_code,
        "-b",
        bar_size,
        "-o",
        "json",
    ]
    if field_map:
        for src, aggs in field_map.items():
            args.extend(["-f", f"{src}:{','.join(aggs)}"])
    return _run_json(args)


def realtime_collect(
    codes: Iterable[str], *, wait: bool = False, until: str | None = None
) -> dict:
    args: list[str] = ["quantrocket", "realtime", "collect", "-d", ",".join(codes), "-o", "json"]
    if wait:
        args.append("--wait")
    if until:
        args.extend(["--until", until])
    return _run_json(args)


def realtime_stop(codes: Iterable[str]) -> dict:
    args = ["quantrocket", "realtime", "stop", "-d", ",".join(codes), "-o", "json"]
    return _run_json(args)


def realtime_list() -> dict:
    return _run_json(["quantrocket", "realtime", "list", "-o", "json"])


def realtime_db(code: str) -> dict:
    return _run_json(["quantrocket", "realtime", "db", "-d", code, "-o", "json"])
