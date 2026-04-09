import sqlite3
import threading
from contextlib import closing

from dotenv import load_dotenv
import os

from vhf.logging.log import logger

load_dotenv()

client = None
_connect_lock = threading.Lock()

# Serialises all DB write access across threads (RLock allows nested acquisition
# by the same thread, e.g. create_reconcile_job → get_reconcile_job).
db_lock = threading.RLock()

# Local SQLite file path. Stored in the persistent data volume so it survives
# container restarts.
_DB_PATH = os.getenv("DB_PATH", "/app/data/vhf.db")


def connect():
    """
    Initialises the global sqlite3 connection (idempotent, thread-safe).

    Uses a local SQLite file at DB_PATH (default: /app/data/vhf.db) which is
    on a persistent volume.
    """
    global client
    # Fast path – already connected.
    if client is not None:
        return

    with _connect_lock:
        # Double-checked locking: another thread may have connected while we waited.
        if client is not None:
            return

        # Ensure the data directory exists.
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)

        client = sqlite3.connect(_DB_PATH, check_same_thread=False)
        logger.info("SQLite connection opened at %s", _DB_PATH)


def verify_connectivity() -> None:
    """Run a lightweight query to confirm the DB is reachable. Raises on failure."""
    connect()
    with closing(client.cursor()) as cursor:
        cursor.execute("SELECT 1")
