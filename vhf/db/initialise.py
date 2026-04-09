from contextlib import closing
from pathlib import Path

from vhf.db import connection


def initialiseDB():
    connection.connect()
    connection.client.sync()

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text()

    with closing(connection.client.cursor()) as cursor:
        cursor.executescript(schema_sql)
        connection.client.commit()
        connection.client.sync()
