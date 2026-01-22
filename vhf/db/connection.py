import os
from contextlib import closing

import libsql
from dotenv import load_dotenv

from vhf.logging.log import logger


client = None

def connect():

    """
    Creates and returns a libSQL client connection.

    Reads connection URL and auth token from environment variables:
    - DB_URL: The connection URL for Turso database (e.g., "libsql://...")
    - DB_TOKEN: The authentication token for Turso database.

    Raises:
        ValueError: If the required environment variables are not set.
    """

    global client
    if client is not None:
        return
    load_dotenv()

    url = os.getenv("DB_URL")
    auth_token = os.getenv("DB_TOKEN")

    if not url:
        raise ValueError("DB_URL environment variable is not set.")

    if not auth_token:
        logger.warn("Warning: DB_TOKEN environment variable is not set. Connecting without auth.")

    # Create the client instance.
    client = libsql.connect(
        "vhf.db",
        sync_url=url,
        auth_token=auth_token
    )
    client.sync()

