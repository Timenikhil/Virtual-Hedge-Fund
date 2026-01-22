from contextlib import closing

from connection import client,connect

def initialiseDB():
    connect()
    client.sync()
    with closing(client.cursor()) as cursor:
        cursor.execute("""
                        CREATE TABLE IF NOT EXISTS portfolios (PID INTEGER PRIMARY KEY AUTOINCREMENT,
                        PNAME TEXT NOT NULL,,
                        WEIGHTS TEXT,
                        SIDS TEXT NOT NULL,
                        LIVE INTEGER NOT NULL )""")
        client.commit()
        client.sync()