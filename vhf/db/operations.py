import json
import math
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List

from fastapi import HTTPException

from vhf.db import connection
from vhf.logging.log import logger
from vhf.models.allocation import AIProviderMode, AllocationMethod, DEFAULT_AI_TIMEOUT_SECONDS
from vhf.models.portfolio import Portfolio, PortfolioCreationRequest, PortfolioList
from vhf.models.reconcile import DEFAULT_RECONCILE_LOCK_TIMEOUT_SECONDS, ReconcileJob
from vhf.models.strategy import Strategy, StrategyList, StrategyPrice
from vhf.quantrocket.allocations import AllocationError, update_account_allocations

DEFAULT_STRATEGY_HISTORY_LIMIT = 5000
DEFAULT_RECONCILE_CLAIM_LIMIT = 100
ORDER_DESC_PREFIX = "-"

ALLOWED_PORTFOLIO_SORT_COLUMNS: dict[str, str] = {
    "id": "PID",
    "pid": "PID",
    "name": "PNAME",
    "pname": "PNAME",
    "date": "DATE",
    "live": "LIVE",
}

ALLOWED_STRATEGY_SORT_COLUMNS: dict[str, str] = {
    "id": "SID",
    "sid": "SID",
    "name": "NAME",
    "category": "CATEGORY",
    "p0": "P0",
    "p1": "P1",
    "p2": "P2",
    "p3": "P3",
    "p4": "P4",
    "p5": "P5",
    "latest": "P5",
}

RECONCILE_JOB_SELECT_COLUMNS = """
    ID,
    PID,
    INTERVAL_SECONDS,
    METHOD,
    THRESHOLD,
    APPLY,
    EXECUTE_TRADES,
    DRY_RUN_TRADES,
    REVIEW_DATE,
    ENABLED,
    AI_PROVIDER_MODE,
    AI_STRICT,
    AI_TIMEOUT_SECONDS,
    AI_CONTEXT,
    CREATED_AT,
    UPDATED_AT,
    LAST_RUN_AT,
    NEXT_RUN_AT,
    LAST_STATUS,
    LAST_ERROR,
    LOCKED_AT,
    LOCKED_BY,
    CONSECUTIVE_ERRORS
"""


def serialize_weights(weights: List[float] | List[str]) -> str:
    return ",".join(map(str, weights))


def deserialize_weights(weights: str | None) -> List[float]:
    if not weights:
        return []
    return [float(x) for x in weights.split(",") if x != ""]


def deserialize_strategies(strategies: str | None) -> list[str]:
    if not strategies:
        return []
    return [s for s in strategies.split(",") if s != ""]


def _json_dumps_safe(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_loads_safe(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON payload from DB")
        return None
    return parsed if isinstance(parsed, dict) else None


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now_dt().isoformat()


def _bool_to_int(value: bool) -> int:
    return 1 if value else 0


def _int_to_bool(value: int | bool) -> bool:
    return bool(int(value))


def _to_allocation_method(raw: str) -> AllocationMethod:
    try:
        return AllocationMethod(raw)
    except ValueError:
        logger.warning("Unknown allocation method '%s'; defaulting to manual", raw)
        return AllocationMethod.manual


def _to_ai_provider_mode(raw: str | None) -> AIProviderMode | None:
    if raw is None or raw == "":
        return None
    try:
        return AIProviderMode(raw)
    except ValueError:
        logger.warning("Unknown AI provider mode '%s'; defaulting to None", raw)
        return None


def _iso_minus_seconds(base_iso: str, seconds: int) -> str:
    try:
        base_dt = datetime.fromisoformat(base_iso)
    except ValueError:
        base_dt = _utc_now_dt()
    return (base_dt - timedelta(seconds=max(int(seconds), 0))).isoformat()


def _validate_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")
    return int(limit)


def _build_order_clause(
    rank_by: str | None,
    *,
    allowed_columns: dict[str, str],
    default_column: str,
) -> str:
    if not rank_by:
        return f"{default_column} ASC"

    raw = rank_by.strip()
    if raw == "":
        return f"{default_column} ASC"

    is_desc = raw.startswith(ORDER_DESC_PREFIX)
    key = raw[1:] if is_desc else raw
    column = allowed_columns.get(key.lower())
    if not column:
        valid = ", ".join(sorted(allowed_columns.keys()))
        raise HTTPException(status_code=400, detail=f"Unsupported rankBy '{rank_by}'. Valid values: {valid}")

    return f"{column} {'DESC' if is_desc else 'ASC'}"


def _row_to_reconcile_job(row: tuple[Any, ...]) -> ReconcileJob:
    return ReconcileJob(
        job_id=int(row[0]),
        portfolio_id=int(row[1]),
        interval_seconds=int(row[2]),
        method=_to_allocation_method(row[3]),
        threshold=float(row[4]),
        apply=_int_to_bool(row[5]),
        execute_trades=_int_to_bool(row[6]),
        dry_run_trades=_int_to_bool(row[7]),
        review_date=row[8],
        enabled=_int_to_bool(row[9]),
        ai_provider_mode=_to_ai_provider_mode(row[10]),
        ai_strict=_int_to_bool(row[11]),
        ai_timeout_seconds=float(row[12]) if row[12] is not None else DEFAULT_AI_TIMEOUT_SECONDS,
        ai_context=_json_loads_safe(row[13]),
        created_at=row[14],
        updated_at=row[15],
        last_run_at=row[16],
        next_run_at=row[17],
        last_status=row[18],
        last_error=row[19],
        locked_at=row[20],
        locked_by=row[21],
        consecutive_errors=int(row[22]) if row[22] is not None else 0,
    )


def _get_portfolio_account(portfolioID: int) -> str | None:
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT ACCOUNT FROM portfolio_accounts WHERE PID = ?
                """,
                (portfolioID,),
            )
            record = cursor.fetchone()
            return record[0] if record else None


def get_portfolio_account(portfolioID: int) -> str | None:
    return _get_portfolio_account(portfolioID)


def set_portfolio_account(portfolioID: int, account: str) -> None:
    """Map a portfolio to a QuantRocket account (1:1)."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO portfolio_accounts (PID, ACCOUNT)
                VALUES (?, ?)
                ON CONFLICT(PID) DO UPDATE SET ACCOUNT=excluded.ACCOUNT
                """,
                (portfolioID, account),
            )
            connection.client.commit()


def _sync_allocations_from_db(portfolioID: int) -> None:
    """
    Sync the given portfolio's strategies/weights to QuantRocket allocations.
    Requires explicit, length-matching weights to avoid silent truncation.
    """
    account = _get_portfolio_account(portfolioID)
    if not account:
        logger.info("No account mapped to portfolio %s; skipping allocation sync", portfolioID)
        return

    portfolio = get_db_portfolio_id(portfolioID)
    logger.info("Syncing allocations for portfolio %s to account %s", portfolioID, account)

    codes = portfolio.strategies
    weights = portfolio.weights or []

    if not weights:
        logger.info(
            "Portfolio %s has no weights yet; skipping allocation sync", portfolioID
        )
        return

    if len(codes) != len(weights):
        logger.warning(
            "Portfolio %s has %d strategies but %d weights; skipping allocation sync",
            portfolioID, len(codes), len(weights),
        )
        return

    try:
        update_account_allocations(account, codes, weights)
    except AllocationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def set_db_pool(pool: PortfolioCreationRequest, date: str) -> int:
    """Store the given portfolio in the database and return the portfolio id."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO portfolios (PNAME, SIDS, LIVE, DATE)
                VALUES (?, ?, 0, ?)
                """,
                (pool.portfolio_name, serialize_weights(pool.strategies), date),
            )
            pid = cursor.lastrowid
            connection.client.commit()

    set_portfolio_account(pid, pool.account)
    return pid


def update_portfolio_strats(portfolioID: int, strats: List[str]) -> None:
    """Update strategy IDs for a portfolio."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                UPDATE portfolios
                SET SIDS = ?
                WHERE PID = ?
                """,
                (serialize_weights(strats), portfolioID),
            )
            connection.client.commit()

    _sync_allocations_from_db(portfolioID)


def update_portfolio_weights(portfolioID: int, weights: List[float]) -> None:
    """Update normalized portfolio weights."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                UPDATE portfolios
                SET WEIGHTS = ?
                WHERE PID = ?
                """,
                (serialize_weights(weights), portfolioID),
            )
            connection.client.commit()

    _sync_allocations_from_db(portfolioID)


def record_allocation_snapshot(
    *,
    portfolio_id: int,
    method: str,
    strategies: List[str],
    raw_weights: List[float],
    target_weights: List[float],
    meta: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> None:
    created = created_at or _utc_now_iso()

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO portfolio_allocations (
                    PID,
                    METHOD,
                    STRATEGIES,
                    RAW_WEIGHTS,
                    TARGET_WEIGHTS,
                    META,
                    CREATED_AT
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio_id,
                    method,
                    serialize_weights(strategies),
                    serialize_weights(raw_weights),
                    serialize_weights(target_weights),
                    _json_dumps_safe(meta),
                    created,
                ),
            )
            connection.client.commit()


def record_rebalance_run(
    *,
    portfolio_id: int,
    account: str | None,
    method: str,
    threshold: float,
    strategies: List[str],
    current_weights: List[float],
    target_weights: List[float],
    trade_weights: List[float],
    status: str,
    meta: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> None:
    created = created_at or _utc_now_iso()

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO rebalance_runs (
                    PID,
                    ACCOUNT,
                    METHOD,
                    THRESHOLD,
                    STRATEGIES,
                    CURRENT_WEIGHTS,
                    TARGET_WEIGHTS,
                    TRADE_WEIGHTS,
                    STATUS,
                    META,
                    CREATED_AT
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio_id,
                    account,
                    method,
                    threshold,
                    serialize_weights(strategies),
                    serialize_weights(current_weights),
                    serialize_weights(target_weights),
                    serialize_weights(trade_weights),
                    status,
                    _json_dumps_safe(meta),
                    created,
                ),
            )
            connection.client.commit()


def create_reconcile_job(
    *,
    portfolio_id: int,
    interval_seconds: int,
    method: AllocationMethod,
    threshold: float,
    apply: bool,
    execute_trades: bool,
    dry_run_trades: bool,
    review_date: str | None,
    ai_provider_mode: AIProviderMode | None = None,
    ai_strict: bool = False,
    ai_timeout_seconds: float = DEFAULT_AI_TIMEOUT_SECONDS,
    ai_context: dict[str, Any] | None = None,
    enabled: bool,
) -> ReconcileJob:
    if interval_seconds <= 0:
        raise HTTPException(status_code=400, detail="interval_seconds must be > 0")
    if threshold < 0:
        raise HTTPException(status_code=400, detail="threshold must be >= 0")
    if not math.isfinite(ai_timeout_seconds) or ai_timeout_seconds <= 0:
        raise HTTPException(status_code=400, detail="ai_timeout_seconds must be a finite number > 0")

    # Fail fast if portfolio does not exist.
    _ = get_db_portfolio_id(portfolio_id)

    now_iso = _utc_now_iso()
    next_run_at = now_iso if enabled else None

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO reconcile_jobs (
                    PID,
                    INTERVAL_SECONDS,
                    METHOD,
                    THRESHOLD,
                    APPLY,
                    EXECUTE_TRADES,
                    DRY_RUN_TRADES,
                    REVIEW_DATE,
                    ENABLED,
                    AI_PROVIDER_MODE,
                    AI_STRICT,
                    AI_TIMEOUT_SECONDS,
                    AI_CONTEXT,
                    CREATED_AT,
                    UPDATED_AT,
                    NEXT_RUN_AT,
                    LOCKED_AT,
                    LOCKED_BY
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    portfolio_id,
                    interval_seconds,
                    method.value,
                    threshold,
                    _bool_to_int(apply),
                    _bool_to_int(execute_trades),
                    _bool_to_int(dry_run_trades),
                    review_date,
                    _bool_to_int(enabled),
                    ai_provider_mode.value if ai_provider_mode else None,
                    _bool_to_int(ai_strict),
                    float(ai_timeout_seconds),
                    _json_dumps_safe(ai_context),
                    now_iso,
                    now_iso,
                    next_run_at,
                ),
            )
            job_id = int(cursor.lastrowid)
            connection.client.commit()

    return get_reconcile_job(job_id)


def get_reconcile_job(job_id: int) -> ReconcileJob:
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT {RECONCILE_JOB_SELECT_COLUMNS}
                FROM reconcile_jobs
                WHERE ID = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Reconcile job not found")
            return _row_to_reconcile_job(row)


def list_reconcile_jobs() -> List[ReconcileJob]:
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT {RECONCILE_JOB_SELECT_COLUMNS}
                FROM reconcile_jobs
                ORDER BY ID ASC
                """
            )
            rows = cursor.fetchall()
            return [_row_to_reconcile_job(row) for row in rows]


def list_due_reconcile_jobs(now_iso: str | None = None) -> List[ReconcileJob]:
    current_iso = now_iso or _utc_now_iso()
    stale_lock_before = _iso_minus_seconds(current_iso, DEFAULT_RECONCILE_LOCK_TIMEOUT_SECONDS)
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT {RECONCILE_JOB_SELECT_COLUMNS}
                FROM reconcile_jobs
                WHERE ENABLED = 1
                  AND (NEXT_RUN_AT IS NULL OR NEXT_RUN_AT <= ?)
                  AND (LOCKED_AT IS NULL OR LOCKED_AT <= ?)
                ORDER BY ID ASC
                """,
                (current_iso, stale_lock_before),
            )
            rows = cursor.fetchall()
            return [_row_to_reconcile_job(row) for row in rows]


def claim_due_reconcile_jobs(
    *,
    worker_id: str,
    now_iso: str | None = None,
    lock_timeout_seconds: int = DEFAULT_RECONCILE_LOCK_TIMEOUT_SECONDS,
    limit: int = DEFAULT_RECONCILE_CLAIM_LIMIT,
) -> List[ReconcileJob]:
    if worker_id.strip() == "":
        raise HTTPException(status_code=400, detail="worker_id must be non-empty")

    current_iso = now_iso or _utc_now_iso()
    stale_lock_before = _iso_minus_seconds(current_iso, lock_timeout_seconds)
    safe_limit = max(int(limit), 1)

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT {RECONCILE_JOB_SELECT_COLUMNS}
                FROM reconcile_jobs
                WHERE ENABLED = 1
                  AND (NEXT_RUN_AT IS NULL OR NEXT_RUN_AT <= ?)
                  AND (LOCKED_AT IS NULL OR LOCKED_AT <= ?)
                ORDER BY ID ASC
                LIMIT ?
                """,
                (current_iso, stale_lock_before, safe_limit),
            )
            rows = cursor.fetchall()

            claimed_ids: list[int] = []
            for row in rows:
                job_id = int(row[0])
                cursor.execute(
                    """
                    UPDATE reconcile_jobs
                    SET LOCKED_AT = ?,
                        LOCKED_BY = ?,
                        UPDATED_AT = ?
                    WHERE ID = ?
                      AND (LOCKED_AT IS NULL OR LOCKED_AT <= ?)
                    """,
                    (current_iso, worker_id, current_iso, job_id, stale_lock_before),
                )
                if cursor.rowcount == 1:
                    claimed_ids.append(job_id)

            connection.client.commit()

    return [get_reconcile_job(job_id) for job_id in claimed_ids]


def set_reconcile_job_enabled(job_id: int, enabled: bool) -> ReconcileJob:
    now_iso = _utc_now_iso()
    next_run = now_iso if enabled else None

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                UPDATE reconcile_jobs
                SET ENABLED = ?,
                    UPDATED_AT = ?,
                    NEXT_RUN_AT = ?,
                    LOCKED_AT = NULL,
                    LOCKED_BY = NULL
                WHERE ID = ?
                """,
                (_bool_to_int(enabled), now_iso, next_run, job_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Reconcile job not found")
            connection.client.commit()

    return get_reconcile_job(job_id)


def update_reconcile_job_after_run(
    *,
    job_id: int,
    last_status: str,
    last_error: str | None,
    next_run_at: str | None,
    last_run_at: str | None = None,
    success: bool = True,
) -> None:
    run_iso = last_run_at or _utc_now_iso()
    updated_iso = _utc_now_iso()

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            # Reset error streak on success; increment on failure.
            if success:
                consecutive_errors_expr = "0"
            else:
                consecutive_errors_expr = "COALESCE(CONSECUTIVE_ERRORS, 0) + 1"

            cursor.execute(
                f"""
                UPDATE reconcile_jobs
                SET LAST_RUN_AT = ?,
                    NEXT_RUN_AT = ?,
                    LAST_STATUS = ?,
                    LAST_ERROR = ?,
                    UPDATED_AT = ?,
                    LOCKED_AT = NULL,
                    LOCKED_BY = NULL,
                    CONSECUTIVE_ERRORS = {consecutive_errors_expr}
                WHERE ID = ?
                """,
                (run_iso, next_run_at, last_status, last_error, updated_iso, job_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Reconcile job not found")
            connection.client.commit()


def record_strategy_price_points(strategy_id: str, points: Iterable[tuple[str, float]]) -> None:
    """Append or upsert historical strategy prices."""
    payload: list[tuple[str, str, float]] = []
    for ts, price in points:
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_price):
            continue
        payload.append((strategy_id, ts, numeric_price))

    if not payload:
        return

    # Write to local SQLite under the lock (fast — no network I/O).
    # Skip the pre-write sync: our local replica is always current (sole writer).
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.executemany(
                """
                INSERT INTO strategy_price_history (SID, TS, PRICE)
                VALUES (?, ?, ?)
                ON CONFLICT(SID, TS) DO UPDATE SET PRICE = excluded.PRICE
                """,
                payload,
            )
            connection.client.commit()



def _get_legacy_strategy_prices(p_values: tuple[Any, ...]) -> list[int]:
    """Takes the 6 P0-P5 values directly (not the full record)."""
    return [int(p_values[i]) for i in range(6)]


def _get_strategy_history(cursor, sid: str, limit: int = DEFAULT_STRATEGY_HISTORY_LIMIT) -> tuple[list[str], list[float]]:
    """Return (dates, prices) for a strategy's price history, ordered by date ascending."""
    cursor.execute(
        """
        SELECT TS, PRICE
        FROM strategy_price_history
        WHERE SID = ?
        ORDER BY TS ASC
        LIMIT ?
        """,
        (sid, max(int(limit), 1)),
    )
    rows = cursor.fetchall()
    dates: list[str] = []
    prices: list[float] = []
    for row in rows:
        try:
            numeric_price = float(row[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_price):
            dates.append(str(row[0]))
            prices.append(round(numeric_price, 4))
    return dates, prices


def get_db_portfolio(name: str) -> Portfolio:
    """Retrieve portfolio by name."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT PID, PNAME, WEIGHTS, SIDS, LIVE, DATE
                FROM portfolios
                WHERE PNAME = ?
                """,
                (name,),
            )
            record = cursor.fetchone()
            if not record:
                raise HTTPException(status_code=404, detail="Portfolio not found")

            return Portfolio(
                portfolio_id=int(record[0]),
                portfolio_name=record[1],
                weights=deserialize_weights(record[2]),
                strategies=deserialize_strategies(record[3]),
                live=bool(int(record[4])),
                date=record[5],
            )


def get_db_portfolio_id(pid: int) -> Portfolio:
    """Retrieve portfolio by id."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT PID, PNAME, WEIGHTS, SIDS, LIVE, DATE
                FROM portfolios
                WHERE PID = ?
                """,
                (pid,),
            )
            record = cursor.fetchone()
            if not record:
                raise HTTPException(status_code=404, detail="Portfolio not found")

            return Portfolio(
                portfolio_id=int(record[0]),
                portfolio_name=record[1],
                weights=deserialize_weights(record[2]),
                strategies=deserialize_strategies(record[3]),
                live=bool(int(record[4])),
                date=record[5],
            )


def get_portfolios_summary() -> list[dict]:
    """
    Return all portfolios with return_percentage and strategy names computed server-side.
    Uses a minimal set of SQL queries — no N+1 fetching.
    """
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute("SELECT PID, PNAME, WEIGHTS, SIDS, DATE, LIVE FROM portfolios ORDER BY PID")
            portfolio_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT SID, PRICE
                FROM strategy_price_history
                WHERE TS IN (SELECT MIN(TS) FROM strategy_price_history GROUP BY SID)
                UNION ALL
                SELECT SID, PRICE
                FROM strategy_price_history
                WHERE TS IN (SELECT MAX(TS) FROM strategy_price_history GROUP BY SID)
                """
            )
            price_rows = cursor.fetchall()

            cursor.execute("SELECT SID, NAME FROM strategies")
            strategy_name_rows = cursor.fetchall()

    strategy_names: dict[str, str] = {sid: name for sid, name in strategy_name_rows}

    # First occurrence per SID = first price, second = last price
    first_prices: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    for sid, price in price_rows:
        p = float(price)
        if sid not in first_prices:
            first_prices[sid] = p
        else:
            last_prices[sid] = p

    result = []
    for pid, pname, weights_str, sids_str, date, live in portfolio_rows:
        strategies = deserialize_strategies(sids_str)
        weights = deserialize_weights(weights_str)
        n = len(strategies)

        initial = 0.0
        final = 0.0
        for i, sid in enumerate(strategies):
            w = weights[i] if i < len(weights) else 0.0
            fp = first_prices.get(sid)
            lp = last_prices.get(sid)
            if fp is not None and lp is not None:
                initial += fp * w
                final += lp * w

        return_pct = ((final - initial) / initial * 100) if initial > 0 else 0.0
        result.append({
            "id": int(pid),
            "name": pname,
            "created_at": date or "",
            "strategy_count": n,
            "strategy_names": [strategy_names.get(sid, sid) for sid in strategies],
            "total_value": round(final),
            "return_percentage": round(return_pct, 4),
            "live": bool(int(live)) if live is not None else False,
        })
    return result


def get_db_strat(sid: str) -> StrategyPrice:
    """Retrieve strategy by id with historical prices and dates when available."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT SID, NAME, DESCRIPTION, CATEGORY, COALESCE(SOURCE, 'local'), P0, P1, P2, P3, P4, P5
                FROM strategies
                WHERE SID = ?
                """,
                (sid,),
            )
            record = cursor.fetchone()
            if not record:
                raise HTTPException(status_code=404, detail="Strategy not found")

            history_dates, history_prices = _get_strategy_history(cursor, sid)
            if history_prices:
                prices = history_prices
                dates = history_dates
            else:
                prices = [float(p) for p in _get_legacy_strategy_prices(record[5:])]
                dates = []

            return StrategyPrice(
                strategy_id=record[0],
                name=record[1],
                description=record[2],
                category=record[3],
                source=record[4],
                prices=prices,
                dates=dates,
            )


def get_ranked_list(rankBy: str | None, limit: int | None) -> PortfolioList:
    """Retrieve portfolios with optional rank/sort and limit."""
    safe_limit = _validate_limit(limit)
    order_clause = _build_order_clause(
        rankBy,
        allowed_columns=ALLOWED_PORTFOLIO_SORT_COLUMNS,
        default_column="PID",
    )

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            query = f"""
                SELECT PID, PNAME, WEIGHTS, SIDS, LIVE, DATE
                FROM portfolios
                ORDER BY {order_clause}
            """
            params: tuple[Any, ...] = ()
            if safe_limit is not None:
                query += " LIMIT ?"
                params = (safe_limit,)

            cursor.execute(query, params)
            records = cursor.fetchall()
            if not records:
                return PortfolioList(portfolios=[])

            mapper = lambda row: Portfolio(
                portfolio_id=int(row[0]),
                portfolio_name=row[1],
                weights=deserialize_weights(row[2]),
                strategies=deserialize_strategies(row[3]),
                live=bool(int(row[4])),
                date=row[5],
            )
            return PortfolioList(portfolios=list(map(mapper, records)))


def get_ranked_strat_list(rankBy: str | None, limit: int | None) -> StrategyList:
    """Retrieve strategies with optional rank/sort and limit."""
    safe_limit = _validate_limit(limit)
    order_clause = _build_order_clause(
        rankBy,
        allowed_columns=ALLOWED_STRATEGY_SORT_COLUMNS,
        default_column="SID",
    )

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            query = f"""
                SELECT SID, NAME, DESCRIPTION, CATEGORY, COALESCE(SOURCE, 'local')
                FROM strategies
                ORDER BY {order_clause}
            """
            params: tuple[Any, ...] = ()
            if safe_limit is not None:
                query += " LIMIT ?"
                params = (safe_limit,)

            cursor.execute(query, params)
            records = cursor.fetchall()
            if not records:
                return StrategyList(strategies=[])

            mapper = lambda row: Strategy(
                strategy_id=row[0],
                name=row[1],
                description=row[2],
                category=row[3],
                source=row[4],
            )
            return StrategyList(strategies=list(map(mapper, records)))


def get_sids(pid: int) -> List[str]:
    """Retrieve strategy IDs by portfolio id."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT SIDS
                FROM portfolios
                WHERE PID = ?
                """,
                (pid,),
            )
            record = cursor.fetchone()
            if not record:
                raise HTTPException(status_code=404, detail="Portfolio not found")

            return deserialize_strategies(record[0])


def upsert_strategy(
    *,
    strategy_id: str,
    name: str,
    description: str,
    category: str,
    source: str = "local",
) -> Strategy:
    """Insert or update a strategy record. Legacy P0-P5 columns are zeroed."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO strategies (SID, NAME, DESCRIPTION, CATEGORY, SOURCE, P0, P1, P2, P3, P4, P5)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
                ON CONFLICT(SID) DO UPDATE SET
                    NAME        = excluded.NAME,
                    DESCRIPTION = excluded.DESCRIPTION,
                    CATEGORY    = excluded.CATEGORY,
                    SOURCE      = excluded.SOURCE
                """,
                (strategy_id, name, description, category, source),
            )
            connection.client.commit()

    return Strategy(
        strategy_id=strategy_id,
        name=name,
        description=description,
        category=category,
    )


def bulk_upsert_strategies(
    strategies: List[dict[str, Any]],
) -> List[Strategy]:
    """
    Upsert multiple strategy records in a single transaction.

    Each dict must have keys: strategy_id, name, description, category.
    Returns the upserted Strategy objects in input order.
    """
    if not strategies:
        return []

    payload: list[tuple] = []
    results: list[Strategy] = []
    for s in strategies:
        sid = str(s.get("strategy_id", "")).strip()
        name = str(s.get("name", "")).strip()
        description = str(s.get("description", "")).strip()
        category = str(s.get("category", "")).strip()
        source = str(s.get("source", "local")).strip()
        if not sid:
            raise HTTPException(status_code=400, detail="strategy_id must be non-empty")
        payload.append((sid, name, description, category, source))
        results.append(Strategy(strategy_id=sid, name=name, description=description, category=category))

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.executemany(
                """
                INSERT INTO strategies (SID, NAME, DESCRIPTION, CATEGORY, SOURCE, P0, P1, P2, P3, P4, P5)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
                ON CONFLICT(SID) DO UPDATE SET
                    NAME        = excluded.NAME,
                    DESCRIPTION = excluded.DESCRIPTION,
                    CATEGORY    = excluded.CATEGORY,
                    SOURCE      = excluded.SOURCE
                """,
                payload,
            )
            connection.client.commit()

    return results


def delete_strategy(strategy_id: str) -> None:
    """Delete a strategy and its price history."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            # Check existence before any destructive operation.
            cursor.execute("SELECT 1 FROM strategies WHERE SID = ?", (strategy_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Strategy not found")
            cursor.execute("DELETE FROM strategy_price_history WHERE SID = ?", (strategy_id,))
            cursor.execute("DELETE FROM strategies WHERE SID = ?", (strategy_id,))
            connection.client.commit()


def get_strategy_price_history_raw(strategy_id: str) -> list[tuple[str, float]]:
    """Return all (ISO date, price) pairs for a strategy, ordered by date ascending."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT TS, PRICE
                FROM strategy_price_history
                WHERE SID = ?
                ORDER BY TS ASC
                """,
                (strategy_id,),
            )
            rows = cursor.fetchall()
    result: list[tuple[str, float]] = []
    for row in rows:
        try:
            price = float(row[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(price):
            result.append((str(row[0]), price))
    return result


def delete_reconcile_job(job_id: int) -> None:
    """Permanently delete a reconcile job by id."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute("SELECT 1 FROM reconcile_jobs WHERE ID = ?", (job_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Reconcile job not found")
            cursor.execute("DELETE FROM reconcile_jobs WHERE ID = ?", (job_id,))
            connection.client.commit()


def update_reconcile_job(
    job_id: int,
    *,
    interval_seconds: int | None = None,
    method: AllocationMethod | None = None,
    threshold: float | None = None,
    apply: bool | None = None,
    execute_trades: bool | None = None,
    dry_run_trades: bool | None = None,
    review_date: str | None = None,
    ai_provider_mode: AIProviderMode | None = None,
    ai_strict: bool | None = None,
    ai_timeout_seconds: float | None = None,
    ai_context: dict[str, Any] | None = None,
) -> ReconcileJob:
    """Partial update of a reconcile job. Only supplied fields are changed."""
    job = get_reconcile_job(job_id)  # 404 if missing

    if interval_seconds is not None and interval_seconds <= 0:
        raise HTTPException(status_code=400, detail="interval_seconds must be > 0")
    if threshold is not None and threshold < 0:
        raise HTTPException(status_code=400, detail="threshold must be >= 0")
    if ai_timeout_seconds is not None and (not math.isfinite(ai_timeout_seconds) or ai_timeout_seconds <= 0):
        raise HTTPException(status_code=400, detail="ai_timeout_seconds must be a finite number > 0")

    new_interval = interval_seconds if interval_seconds is not None else job.interval_seconds
    new_method = method if method is not None else job.method
    new_threshold = threshold if threshold is not None else job.threshold
    new_apply = apply if apply is not None else job.apply
    new_execute_trades = execute_trades if execute_trades is not None else job.execute_trades
    new_dry_run_trades = dry_run_trades if dry_run_trades is not None else job.dry_run_trades
    new_review_date = review_date if review_date is not None else job.review_date
    new_ai_mode = ai_provider_mode if ai_provider_mode is not None else job.ai_provider_mode
    new_ai_strict = ai_strict if ai_strict is not None else job.ai_strict
    new_ai_timeout = ai_timeout_seconds if ai_timeout_seconds is not None else job.ai_timeout_seconds
    new_ai_context = ai_context if ai_context is not None else job.ai_context

    now_iso = _utc_now_iso()
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                UPDATE reconcile_jobs
                SET INTERVAL_SECONDS   = ?,
                    METHOD             = ?,
                    THRESHOLD          = ?,
                    APPLY              = ?,
                    EXECUTE_TRADES     = ?,
                    DRY_RUN_TRADES     = ?,
                    REVIEW_DATE        = ?,
                    AI_PROVIDER_MODE   = ?,
                    AI_STRICT          = ?,
                    AI_TIMEOUT_SECONDS = ?,
                    AI_CONTEXT         = ?,
                    UPDATED_AT         = ?
                WHERE ID = ?
                """,
                (
                    new_interval,
                    new_method.value,
                    new_threshold,
                    _bool_to_int(new_apply),
                    _bool_to_int(new_execute_trades),
                    _bool_to_int(new_dry_run_trades),
                    new_review_date,
                    new_ai_mode.value if new_ai_mode else None,
                    _bool_to_int(new_ai_strict),
                    float(new_ai_timeout),
                    _json_dumps_safe(new_ai_context),
                    now_iso,
                    job_id,
                ),
            )
            connection.client.commit()

    return get_reconcile_job(job_id)


def get_allocation_history(portfolio_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent allocation snapshots for a portfolio, newest first."""
    safe_limit = max(1, min(int(limit), 500))
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT ID, PID, METHOD, STRATEGIES, RAW_WEIGHTS, TARGET_WEIGHTS, META, CREATED_AT
                FROM portfolio_allocations
                WHERE PID = ?
                ORDER BY CREATED_AT DESC
                LIMIT ?
                """,
                (portfolio_id, safe_limit),
            )
            rows = cursor.fetchall()
    result = []
    for row in rows:
        strategies = deserialize_strategies(row[3])
        raw_weights = deserialize_weights(row[4])
        target_weights = deserialize_weights(row[5])
        result.append({
            "id": int(row[0]),
            "portfolio_id": int(row[1]),
            "method": row[2],
            "strategies": strategies,
            "raw_weights": raw_weights,
            "target_weights": target_weights,
            "meta": _json_loads_safe(row[6]),
            "created_at": row[7],
        })
    return result


def delete_portfolio(portfolio_id: int) -> None:
    """Delete a portfolio and all its associated data (accounts, allocations, rebalances, jobs)."""
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute("SELECT 1 FROM portfolios WHERE PID = ?", (portfolio_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Portfolio not found")
            # Delete in dependency order.
            cursor.execute("DELETE FROM reconcile_jobs WHERE PID = ?", (portfolio_id,))
            cursor.execute("DELETE FROM rebalance_runs WHERE PID = ?", (portfolio_id,))
            cursor.execute("DELETE FROM portfolio_allocations WHERE PID = ?", (portfolio_id,))
            cursor.execute("DELETE FROM portfolio_accounts WHERE PID = ?", (portfolio_id,))
            cursor.execute("DELETE FROM portfolios WHERE PID = ?", (portfolio_id,))
            connection.client.commit()


def update_portfolio(
    portfolio_id: int,
    *,
    portfolio_name: str | None = None,
    account: str | None = None,
) -> Portfolio:
    """Update a portfolio's name and/or account mapping."""
    # 404 if missing.
    portfolio = get_db_portfolio_id(portfolio_id)
    now_iso = _utc_now_iso()

    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            if portfolio_name is not None:
                new_name = portfolio_name.strip()
                if not new_name:
                    raise HTTPException(status_code=400, detail="portfolio_name must be non-empty")
                cursor.execute(
                    "UPDATE portfolios SET PNAME = ? WHERE PID = ?",
                    (new_name, portfolio_id),
                )
            if account is not None:
                new_account = account.strip()
                if not new_account:
                    raise HTTPException(status_code=400, detail="account must be non-empty")
                cursor.execute(
                    """
                    INSERT INTO portfolio_accounts (PID, ACCOUNT)
                    VALUES (?, ?)
                    ON CONFLICT(PID) DO UPDATE SET ACCOUNT = excluded.ACCOUNT
                    """,
                    (portfolio_id, new_account),
                )
            connection.client.commit()

    return get_db_portfolio_id(portfolio_id)


def get_rebalance_history(portfolio_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent rebalance runs for a portfolio, newest first."""
    safe_limit = max(1, min(int(limit), 500))
    with connection.db_lock:
        connection.connect()
        with closing(connection.client.cursor()) as cursor:
            cursor.execute(
                """
                SELECT ID, PID, ACCOUNT, METHOD, THRESHOLD, STRATEGIES,
                       CURRENT_WEIGHTS, TARGET_WEIGHTS, TRADE_WEIGHTS, STATUS, META, CREATED_AT
                FROM rebalance_runs
                WHERE PID = ?
                ORDER BY CREATED_AT DESC
                LIMIT ?
                """,
                (portfolio_id, safe_limit),
            )
            rows = cursor.fetchall()
    result = []
    for row in rows:
        strategies = deserialize_strategies(row[5])
        result.append({
            "id": int(row[0]),
            "portfolio_id": int(row[1]),
            "account": row[2],
            "method": row[3],
            "threshold": float(row[4]),
            "strategies": strategies,
            "current_weights": deserialize_weights(row[6]),
            "target_weights": deserialize_weights(row[7]),
            "trade_weights": deserialize_weights(row[8]),
            "status": row[9],
            "meta": _json_loads_safe(row[10]),
            "created_at": row[11],
        })
    return result
