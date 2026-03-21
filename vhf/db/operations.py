import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, List

from fastapi import HTTPException

from vhf.db import connection
from vhf.logging.log import logger
from vhf.models.allocation import AllocationMethod
from vhf.models.portfolio import Portfolio, PortfolioCreationRequest, PortfolioList
from vhf.models.reconcile import ReconcileJob
from vhf.models.strategy import Strategy, StrategyList, StrategyPrice
from vhf.quantrocket.allocations import AllocationError, update_account_allocations


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        created_at=row[10],
        updated_at=row[11],
        last_run_at=row[12],
        next_run_at=row[13],
        last_status=row[14],
        last_error=row[15],
    )


def _get_portfolio_account(portfolioID: int) -> str | None:
    connection.connect()
    connection.client.sync()
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
    """
    Map a portfolio to a QuantRocket account (1:1).
    """
    connection.connect()
    connection.client.sync()
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
        connection.client.sync()


def _sync_allocations_from_db(portfolioID: int) -> None:
    """
    Sync the given portfolio's strategies/weights to QuantRocket allocations
    based on the mapped account. No-op if no mapping exists.
    """
    account = _get_portfolio_account(portfolioID)
    if not account:
        logger.info("No account mapped to portfolio %s; skipping allocation sync", portfolioID)
        return

    portfolio = get_db_portfolio_id(portfolioID)
    logger.info("Syncing allocations for portfolio %s to account %s", portfolioID, account)

    codes = portfolio.strategies
    weights = portfolio.weights
    if len(codes) != len(weights):
        min_len = min(len(codes), len(weights))
        logger.warning(
            "Strategy/weight length mismatch for portfolio %s: %s vs %s. Truncating to %s.",
            portfolioID,
            len(codes),
            len(weights),
            min_len,
        )
        codes = codes[:min_len]
        weights = weights[:min_len]

    try:
        update_account_allocations(account, codes, weights)
    except AllocationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def set_db_pool(pool: PortfolioCreationRequest, date: str) -> int:
    """
    Store the given Portfolio in the database and return the portfolio id.
    """
    connection.connect()
    connection.client.sync()
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
        connection.client.sync()

    set_portfolio_account(pid, pool.account)
    return pid


def update_portfolio_strats(portfolioID: int, strats: List[str]) -> None:
    """
    Update strategy IDs for a portfolio.
    """
    connection.connect()
    connection.client.sync()
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
        connection.client.sync()

    _sync_allocations_from_db(portfolioID)


def update_portfolio_weights(portfolioID: int, weights: List[float]) -> None:
    """
    Update normalized portfolio weights.
    """
    connection.connect()
    connection.client.sync()
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
        connection.client.sync()

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
    created = created_at or datetime.utcnow().isoformat()

    connection.connect()
    connection.client.sync()
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
        connection.client.sync()


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
    created = created_at or datetime.utcnow().isoformat()

    connection.connect()
    connection.client.sync()
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
        connection.client.sync()


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
    enabled: bool,
) -> ReconcileJob:
    if interval_seconds <= 0:
        raise HTTPException(status_code=400, detail="interval_seconds must be > 0")
    if threshold < 0:
        raise HTTPException(status_code=400, detail="threshold must be >= 0")
    # Fail fast if portfolio does not exist.
    _ = get_db_portfolio_id(portfolio_id)

    now_iso = _utc_now_iso()
    next_run_at = now_iso if enabled else None

    connection.connect()
    connection.client.sync()
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
                CREATED_AT,
                UPDATED_AT,
                NEXT_RUN_AT
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now_iso,
                now_iso,
                next_run_at,
            ),
        )
        job_id = int(cursor.lastrowid)
        connection.client.commit()
        connection.client.sync()

    return get_reconcile_job(job_id)


def get_reconcile_job(job_id: int) -> ReconcileJob:
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT
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
                CREATED_AT,
                UPDATED_AT,
                LAST_RUN_AT,
                NEXT_RUN_AT,
                LAST_STATUS,
                LAST_ERROR
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
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT
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
                CREATED_AT,
                UPDATED_AT,
                LAST_RUN_AT,
                NEXT_RUN_AT,
                LAST_STATUS,
                LAST_ERROR
            FROM reconcile_jobs
            ORDER BY ID ASC
            """
        )
        rows = cursor.fetchall()
        return [_row_to_reconcile_job(row) for row in rows]


def list_due_reconcile_jobs(now_iso: str | None = None) -> List[ReconcileJob]:
    current_iso = now_iso or _utc_now_iso()
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT
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
                CREATED_AT,
                UPDATED_AT,
                LAST_RUN_AT,
                NEXT_RUN_AT,
                LAST_STATUS,
                LAST_ERROR
            FROM reconcile_jobs
            WHERE ENABLED = 1
              AND (NEXT_RUN_AT IS NULL OR NEXT_RUN_AT <= ?)
            ORDER BY ID ASC
            """,
            (current_iso,),
        )
        rows = cursor.fetchall()
        return [_row_to_reconcile_job(row) for row in rows]


def set_reconcile_job_enabled(job_id: int, enabled: bool) -> ReconcileJob:
    now_iso = _utc_now_iso()
    next_run = now_iso if enabled else None

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            UPDATE reconcile_jobs
            SET ENABLED = ?, UPDATED_AT = ?, NEXT_RUN_AT = ?
            WHERE ID = ?
            """,
            (_bool_to_int(enabled), now_iso, next_run, job_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reconcile job not found")
        connection.client.commit()
        connection.client.sync()

    return get_reconcile_job(job_id)


def update_reconcile_job_after_run(
    *,
    job_id: int,
    last_status: str,
    last_error: str | None,
    next_run_at: str | None,
    last_run_at: str | None = None,
) -> None:
    run_iso = last_run_at or _utc_now_iso()
    updated_iso = _utc_now_iso()

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            UPDATE reconcile_jobs
            SET LAST_RUN_AT = ?,
                NEXT_RUN_AT = ?,
                LAST_STATUS = ?,
                LAST_ERROR = ?,
                UPDATED_AT = ?
            WHERE ID = ?
            """,
            (run_iso, next_run_at, last_status, last_error, updated_iso, job_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reconcile job not found")
        connection.client.commit()
        connection.client.sync()


def get_db_portfolio(name: str) -> Portfolio:
    """
    Retrieve Portfolio by Name.
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT PID, PNAME, WEIGHTS, SIDS, LIVE
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
        )


def get_db_portfolio_id(pid: int) -> Portfolio:
    """
    Retrieve Portfolio by Id.
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT PID, PNAME, WEIGHTS, SIDS, LIVE
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
        )


def get_db_strat(sid: str) -> StrategyPrice:
    """
    Retrieve Strategy by Id.
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT SID, NAME, DESCRIPTION, CATEGORY, P0, P1, P2, P3, P4, P5
            FROM strategies
            WHERE SID = ?
            """,
            (sid,),
        )
        record = cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="Strategy not found")

        return StrategyPrice(
            strategy_id=record[0],
            name=record[1],
            description=record[2],
            category=record[3],
            prices=[record[4], record[5], record[6], record[7], record[8], record[9]],
        )


def get_ranked_list(rankBy: str, limit: int | None) -> PortfolioList:
    """
    Retrieve portfolios optionally capped by limit.
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        if limit:
            cursor.execute(
                """
                SELECT PID, PNAME, WEIGHTS, SIDS, LIVE, DATE
                FROM portfolios
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT PID, PNAME, WEIGHTS, SIDS, LIVE, DATE
                FROM portfolios
                """
            )

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


def get_ranked_strat_list(rankBy: str, limit: int | None) -> StrategyList:
    """
    Retrieve strategies optionally capped by limit.
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        if limit:
            cursor.execute(
                """
                SELECT SID, NAME, DESCRIPTION, CATEGORY
                FROM strategies
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT SID, NAME, DESCRIPTION, CATEGORY
                FROM strategies
                """
            )

        records = cursor.fetchall()
        if not records:
            return StrategyList(strategies=[])

        mapper = lambda row: Strategy(
            strategy_id=row[0],
            name=row[1],
            description=row[2],
            category=row[3],
        )
        return StrategyList(strategies=list(map(mapper, records)))


def get_sids(pid: int) -> List[str]:
    """
    Retrieve strategy IDs by portfolio id.
    """
    connection.connect()
    connection.client.sync()
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
