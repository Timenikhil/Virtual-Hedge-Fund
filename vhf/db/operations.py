from contextlib import closing
from typing import List

from fastapi import HTTPException

from vhf.db.connection import client, connect
from vhf.models.portfolio import PortfolioRequest, Portfolio

def serialize_weights(weights) -> str:
    return ",".join(map(str,weights))

def deserialize_weights(weights) -> List[float]:
    return [] if weights is None else [float(x) for x in weights.split(",")]

def deserialize_strategies(strategies) -> list[str]:
    return strategies.split(",")

def set_db_pool(pool:PortfolioRequest) -> int:
    """

    Store the given Portfolio in the database and return the portfolio id

    :param pool: Selected pool
    :return: portfolio id
    """
    connect()
    client.sync()
    with closing(client.cursor()) as cursor:
        cursor.execute('''
                       INSERT INTO portfolios (PNAME,SIDS,LIVE)
                       VALUES (?,?,0)''', (pool.portfolio_name, serialize_weights(pool.strategies)))
        client.commit()
        client.sync()
        return cursor.lastrowid

def update_portfolio_weights(portfolioID:int, weights:List[float]) -> None:
    """

    Store the given Portfolio weights
    :param portfolioID: portfolio id
    :param weights: weights

    """
    connect()
    client.sync()
    with closing(client.cursor()) as cursor:
        cursor.execute('''
                       UPDATE portfolios
                       SET WEIGHTS = ?
                       WHERE PID = ?''',
                       (serialize_weights(weights), portfolioID))
        client.commit()
        client.sync()

def get_db_portfolio(name:str) -> Portfolio:
    """

    Retrieve Portfolio by Name

    :param name: Portfolio
    :return:
    """
    connect()
    client.sync()
    with closing(client.cursor()) as cursor:
        cursor.execute('''
                        SELECT PID, PNAME, WEIGHTS, SIDS, LIVE
                        FROM portfolios 
                        WHERE PNAME  = ?''', (name,))
        record = cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return Portfolio(portfolio_id=int(record[0]),portfolio_name=record[1],weights = deserialize_weights(record[2]),strategies=deserialize_strategies(record[3]),live= bool(int(record[4])))
