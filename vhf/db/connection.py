import threading
from contextlib import closing

import libsql
from dotenv import load_dotenv
import os

from vhf.logging.log import logger

load_dotenv()

client = None
_connect_lock = threading.Lock()


def connect():
    """
    Initialises the global libSQL client connection (idempotent, thread-safe).

    Reads connection URL and auth token from environment variables:
    - DB_URL: The connection URL for Turso database (e.g., "libsql://...")
    - DB_TOKEN: The authentication token for Turso database.

    Raises:
        ValueError: If DB_URL is not set.
    """
    global client
    # Fast path – already connected.
    if client is not None:
        return

    with _connect_lock:
        # Double-checked locking: another thread may have connected while we waited.
        if client is not None:
            return

        url = os.getenv("DB_URL")
        auth_token = os.getenv("DB_TOKEN")

        if not url:
            raise ValueError("DB_URL environment variable is not set.")

        if not auth_token:
            logger.warning("DB_TOKEN environment variable is not set. Connecting without auth.")

        client = libsql.connect(
            "vhf.db",
            sync_url=url,
            auth_token=auth_token,
        )
        client.sync()


def verify_connectivity() -> None:
    """Run a lightweight query to confirm the DB is reachable. Raises on failure."""
    connect()
    with closing(client.cursor()) as cursor:
        cursor.execute("SELECT 1")
