from contextlib import closing

from vhf.db import connection


def initialiseDB():
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            """
                        CREATE TABLE IF NOT EXISTS portfolios (PID INTEGER PRIMARY KEY AUTOINCREMENT,
                        PNAME TEXT NOT NULL,
                        WEIGHTS TEXT,
                        SIDS TEXT NOT NULL,
                        DATE TEXT NOT NULL,
                        LIVE INTEGER NOT NULL);""")
        cursor.execute("""
                        CREATE TABLE IF NOT EXISTS strategies (SID TEXT PRIMARY KEY,
                        NAME TEXT NOT NULL,
                        DESCRIPTION TEXT NOT NULL,
                        CATEGORY TEXT NOT NULL,
                        P0 INTEGER NOT NULL,
                        P1 INTEGER NOT NULL,
                        P2 INTEGER NOT NULL,
                        P3 INTEGER NOT NULL,
                        P4 INTEGER NOT NULL,
                        P5 INTEGER NOT NULL);
                        """
        )
        connection.client.commit()
        connection.client.sync()
