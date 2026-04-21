"""One-shot seeder for the load-test SQLite database.

Writes a fresh DB at ``DB_PATH`` (default ``/tmp/vhf_load.db``) containing
20 portfolios × 10 strategies × 252 days of synthetic GBM price history.

Set ``DB_PATH`` *before* running so ``vhf.db.connection`` captures the
override at import time. Idempotent — deletes any existing file first.

Usage:
    DB_PATH=/tmp/vhf_load.db python -m tests.load.seed
"""

from __future__ import annotations

import math
import os
import random
import sys
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

DEFAULT_DB_PATH = "/tmp/vhf_load.db"
os.environ.setdefault("DB_PATH", DEFAULT_DB_PATH)

from vhf.db import connection  # noqa: E402
from vhf.db.initialise import initialiseDB  # noqa: E402


NUM_STRATEGIES = 10
NUM_PORTFOLIOS = 20
TRADING_DAYS = 252
START_DATE = date(2025, 1, 2)


def _gbm(start: float, mu: float, sigma: float, n: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    dt = 1 / 252
    prices = [start]
    for _ in range(n - 1):
        prices.append(
            prices[-1]
            * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * rng.gauss(0, 1))
        )
    return prices


def _trading_days(n: int) -> list[str]:
    out: list[str] = []
    d = START_DATE
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def main() -> int:
    db_path = os.environ["DB_PATH"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Fresh start: drop the file so schema + rows are deterministic.
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass

    initialiseDB()
    connection.connect()
    client = connection.client

    rng = random.Random(42)
    strategies = [
        {
            "sid": f"load-strat-{i:02d}",
            "name": f"Load Strategy {i:02d}",
            "description": f"Synthetic strategy {i} for load testing",
            "category": rng.choice(["momentum", "mean_reversion", "value", "ml", "pairs"]),
            "mu": rng.uniform(0.04, 0.22),
            "sigma": rng.uniform(0.05, 0.30),
            "seed": 1000 + i,
        }
        for i in range(NUM_STRATEGIES)
    ]

    dates = _trading_days(TRADING_DAYS)
    price_rows: list[tuple[str, str, float]] = []
    for s in strategies:
        prices = _gbm(1000.0, s["mu"], s["sigma"], TRADING_DAYS, s["seed"])
        for ts, px in zip(dates, prices):
            price_rows.append((s["sid"], ts, round(px, 4)))

    with closing(client.cursor()) as cur:
        cur.executemany(
            """
            INSERT INTO strategies (SID, NAME, DESCRIPTION, CATEGORY, SOURCE, P0, P1, P2, P3, P4, P5)
            VALUES (?, ?, ?, ?, 'local', 0, 0, 0, 0, 0, 0)
            ON CONFLICT(SID) DO UPDATE SET
                NAME=excluded.NAME,
                DESCRIPTION=excluded.DESCRIPTION,
                CATEGORY=excluded.CATEGORY
            """,
            [(s["sid"], s["name"], s["description"], s["category"]) for s in strategies],
        )

        cur.executemany(
            "INSERT OR IGNORE INTO strategy_price_history (SID, TS, PRICE) VALUES (?, ?, ?)",
            price_rows,
        )

        today = date.today().isoformat()
        portfolio_rows: list[tuple[str, str, int, str]] = []
        for i in range(NUM_PORTFOLIOS):
            k = rng.randint(5, NUM_STRATEGIES)
            sids = rng.sample([s["sid"] for s in strategies], k)
            portfolio_rows.append(
                (f"load-portfolio-{i:02d}", ",".join(sids), 0, today)
            )

        cur.executemany(
            "INSERT INTO portfolios (PNAME, SIDS, LIVE, DATE) VALUES (?, ?, ?, ?)",
            portfolio_rows,
        )
        client.commit()

        cur.execute("SELECT PID FROM portfolios ORDER BY PID")
        pids = [row[0] for row in cur.fetchall()]

    print(f"Seeded {db_path}:")
    print(f"  strategies      : {NUM_STRATEGIES}")
    print(f"  portfolios      : {NUM_PORTFOLIOS}  (PIDs {pids[0]}..{pids[-1]})")
    print(f"  price rows      : {len(price_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
