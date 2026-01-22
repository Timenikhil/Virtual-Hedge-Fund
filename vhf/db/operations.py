from contextlib import closing

from vhf.db.connection import client, connect
from vhf.models.portfolio import PortfolioRequest, Portfolio


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
                       VALUES (?,?,0)''', (pool.portfolio_name, ",".join(pool.strategies)))
        client.commit()
        client.sync()
        return cursor.lastrowid

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
                        SELECT * FROM portfolios 
                        WHERE PNAME  = ?''', (name,))
        record = cursor.fetchone()
        return Portfolio(portfolio_id=int(record[0]),portfolio_name=record[1],weights = [float(x) for x in record[2].split(",")],strategies=record[3].split(","),live= bool(int(record[4])))
