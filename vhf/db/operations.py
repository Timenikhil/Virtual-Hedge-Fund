from datetime import datetime
from contextlib import closing
from typing import List

from fastapi import HTTPException

from vhf.db import connection
from vhf.models.portfolio import Portfolio, PortfolioList, PortfolioCreationRequest
from vhf.models.strategy import StrategyList, Strategy, StrategyPrice
from vhf.quantrocket.allocations import AllocationError, update_account_allocations
from vhf.logging.log import logger


def serialize_weights(weights) -> str:
    return ",".join(map(str, weights))


def deserialize_weights(weights) -> List[float]:
    return [] if weights is None else [float(x) for x in weights.split(",")]


def deserialize_strategies(strategies) -> list[str]:
    return strategies.split(",")


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
        logger.info(
            "No account mapped to portfolio %s; skipping allocation sync", portfolioID
        )
        return

    portfolio = get_db_portfolio_id(portfolioID)
    logger.info(
        "Syncing allocations for portfolio %s to account %s",
        portfolioID,
        account,
    )
    # Align lengths; if mismatch, truncate to shortest.
    codes = portfolio.strategies
    weights = portfolio.weights
    if len(codes) != len(weights):
        min_len = min(len(codes), len(weights))
        codes = codes[:min_len]
        weights = weights[:min_len]
    try:
        update_account_allocations(account, codes, weights)
    except AllocationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def set_db_pool(pool: PortfolioCreationRequest, date: str) -> int:
    """

    Store the given Portfolio in the database and return the portfolio id

    :param pool: Selected pool
    :return: portfolio id
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                       INSERT INTO portfolios (PNAME,SIDS,LIVE,DATE)
                       VALUES (?,?,0,?)""",
            (pool.portfolio_name, serialize_weights(pool.strategies), date),
        )
        pid = cursor.lastrowid
        connection.client.commit()
        connection.client.sync()
    set_portfolio_account(pid, pool.account)
    return pid


def update_portfolio_strats(portfolioID: int, strats: List[str]) -> None:
    """

    Store the given Portfolio weights
    :param portfolioID: portfolio id
    :param strats: weights

    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                       UPDATE portfolios
                       SET SIDS = ?
                       WHERE PID = ?""",
            (serialize_weights(strats), portfolioID),
        )
        connection.client.commit()
        connection.client.sync()
    _sync_allocations_from_db(portfolioID)


def update_portfolio_weights(portfolioID: int, weights: List[float]) -> None:
    """

    Store the given Portfolio weights
    :param portfolioID: portfolio id
    :param weights: weights

    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                       UPDATE portfolios
                       SET WEIGHTS = ?
                       WHERE PID = ?""",
            (serialize_weights(weights), portfolioID),
        )
        connection.client.commit()
        connection.client.sync()
    _sync_allocations_from_db(portfolioID)


def get_db_portfolio(name: str) -> Portfolio:
    """

    Retrieve Portfolio by Name

    :param name: Portfolio
    :return:
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                        SELECT PID, PNAME, WEIGHTS, SIDS, LIVE
                        FROM portfolios 
                        WHERE PNAME  = ?""",
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

    Retrieve Portfolio by Id

    :param pid: Portfolio
    :return:
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT PID, PNAME, WEIGHTS, SIDS, LIVE
            FROM portfolios
            WHERE PID  = ?""",
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

def delete_db_portfolio_id(pid: int) :
    """

    Delete Portfolio by Id

    :param pid: Portfolio
    :return:
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            DELETE FROM portfolios
            WHERE PID  = ?""",
            (pid,),
        )
        connection.client.commit()
        connection.client.sync()
        if cursor.rowcount == 0:
            print(f"No portfolio found with PID: {pid}")

def get_db_strat(sid: str) -> StrategyPrice:
    """

    Retrieve Strategy by Id

    :param sid: Strategy
    :return:
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            SELECT SID, NAME, DESCRIPTION, CATEGORY,P0,P1,P2,P3,P4,P5
            FROM strategies
            WHERE SID  = ?""",
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
    Retrieve limit Portfolio by rankBy
    :param rankBy:
    :param limit:
    :return:
    """

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        if limit:
            cursor.execute(
                """
                           SELECT PID, PNAME, WEIGHTS, SIDS, LIVE,DATE
                           FROM portfolios
                           LIMIT ?
                           """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                           SELECT PID, PNAME, WEIGHTS, SIDS, LIVE,DATE
                           FROM portfolios
                           """
            )
        record = cursor.fetchall()
        if not record:
            return PortfolioList(portfolios=[])
        mapper = lambda row: Portfolio(
            portfolio_id=int(row[0]),
            portfolio_name=row[1],
            weights=deserialize_weights(row[2]),
            strategies=deserialize_strategies(row[3]),
            live=bool(int(row[4])),
            date=row[5],
        )
        return PortfolioList(portfolios=list(map(mapper, record)))


def get_ranked_strat_list(rankBy: str, limit: int | None) -> StrategyList:
    """
    Retrieve limit strategies by rankBy
    :param rankBy:
    :param limit:
    :return:
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
        record = cursor.fetchall()
        if not record:
            return StrategyList(strategies=[])
        mapper = lambda row: Strategy(
            strategy_id=row[0], name=row[1], description=row[2], category=row[3]
        )
        return StrategyList(strategies=list(map(mapper, record)))


def get_sids(pid: int) -> List[str]:
    """

    Retrieve Sids by Portfolio id

    :param name: Portfolio
    :return:
    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                       SELECT SIDS
                       FROM portfolios
                       WHERE PID  = ?""",
            (pid,),
        )
        record = cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return deserialize_strategies(record[0])

def set_db_allocator(portfolioID : int,allocator : str):
    """
    Store the given Portfolio Rebalancer
    :param portfolioID: portfolio id
    :param allocator : allocator

    """
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            UPDATE portfolios
            SET REBALANCER = ?
            WHERE PID = ?""",
            (serialize_weights(allocator), portfolioID),
        )
        connection.client.commit()
        connection.client.sync()
    _sync_allocations_from_db(portfolioID)