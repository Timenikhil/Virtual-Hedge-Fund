from contextlib import closing

from vhf.db import connection


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def _ensure_column(cursor, table: str, column: str, definition: str) -> None:
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialiseDB():
    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        try:
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
                CREATE TABLE IF NOT EXISTS strategy_price_history (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    SID TEXT NOT NULL,
                    TS TEXT NOT NULL,
                    PRICE REAL NOT NULL,
                    UNIQUE(SID, TS)
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_strategy_price_history_sid_ts
                ON strategy_price_history (SID, TS);
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

            # Backward-compatible schema evolution for existing DBs.
            _ensure_column(cursor, "reconcile_jobs", "AI_PROVIDER_MODE", "TEXT")
            _ensure_column(cursor, "reconcile_jobs", "AI_STRICT", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(cursor, "reconcile_jobs", "AI_TIMEOUT_SECONDS", "REAL NOT NULL DEFAULT 10.0")
            _ensure_column(cursor, "reconcile_jobs", "AI_CONTEXT", "TEXT")
            _ensure_column(cursor, "reconcile_jobs", "LOCKED_AT", "TEXT")
            _ensure_column(cursor, "reconcile_jobs", "LOCKED_BY", "TEXT")
            _ensure_column(cursor, "reconcile_jobs", "CONSECUTIVE_ERRORS", "INTEGER NOT NULL DEFAULT 0")

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reconcile_jobs_due
                ON reconcile_jobs (ENABLED, NEXT_RUN_AT);
                """
            )

            connection.client.commit()
            connection.client.sync()
        except Exception:
            try:
                connection.client.rollback()
            except Exception:
                pass
            raise
