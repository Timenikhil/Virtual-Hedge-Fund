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
                        LIVE INTEGER NOT NULL )"""
        )
        connection.client.commit()
        connection.client.sync()
