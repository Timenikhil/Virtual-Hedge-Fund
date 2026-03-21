from contextlib import closing

from vhf.db import connection


def initialiseDB():
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolios (
                PID INTEGER PRIMARY KEY AUTOINCREMENT,
                PNAME TEXT NOT NULL,
                WEIGHTS TEXT,
                SIDS TEXT NOT NULL,
                DATE TEXT NOT NULL,
                LIVE INTEGER NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS strategies (
                SID TEXT PRIMARY KEY,
                NAME TEXT NOT NULL,
                DESCRIPTION TEXT NOT NULL,
                CATEGORY TEXT NOT NULL,
                P0 INTEGER NOT NULL,
                P1 INTEGER NOT NULL,
                P2 INTEGER NOT NULL,
                P3 INTEGER NOT NULL,
                P4 INTEGER NOT NULL,
                P5 INTEGER NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_accounts (
                PID INTEGER PRIMARY KEY,
                ACCOUNT TEXT NOT NULL,
                UNIQUE(ACCOUNT)
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_allocations (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                PID INTEGER NOT NULL,
                METHOD TEXT NOT NULL,
                STRATEGIES TEXT NOT NULL,
                RAW_WEIGHTS TEXT NOT NULL,
                TARGET_WEIGHTS TEXT NOT NULL,
                META TEXT,
                CREATED_AT TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rebalance_runs (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                PID INTEGER NOT NULL,
                ACCOUNT TEXT,
                METHOD TEXT NOT NULL,
                THRESHOLD REAL NOT NULL,
                STRATEGIES TEXT NOT NULL,
                CURRENT_WEIGHTS TEXT NOT NULL,
                TARGET_WEIGHTS TEXT NOT NULL,
                TRADE_WEIGHTS TEXT NOT NULL,
                STATUS TEXT NOT NULL,
                META TEXT,
                CREATED_AT TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reconcile_jobs (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                PID INTEGER NOT NULL,
                INTERVAL_SECONDS INTEGER NOT NULL,
                METHOD TEXT NOT NULL,
                THRESHOLD REAL NOT NULL,
                APPLY INTEGER NOT NULL,
                EXECUTE_TRADES INTEGER NOT NULL,
                DRY_RUN_TRADES INTEGER NOT NULL,
                REVIEW_DATE TEXT,
                ENABLED INTEGER NOT NULL,
                CREATED_AT TEXT NOT NULL,
                UPDATED_AT TEXT NOT NULL,
                LAST_RUN_AT TEXT,
                NEXT_RUN_AT TEXT,
                LAST_STATUS TEXT,
                LAST_ERROR TEXT
            );
            """
        )
        connection.client.commit()
        connection.client.sync()
