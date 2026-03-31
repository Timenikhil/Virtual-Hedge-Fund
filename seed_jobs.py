"""
Seed one reconcile job per portfolio.
Each job runs score_weighted rebalancing monthly (every 21 trading days ≈ 1814400s),
with dry-run trades enabled and a 5% threshold.
"""
from contextlib import closing
from datetime import datetime, timezone
from vhf.db import connection

JOBS = [
    {'pid': 21, 'account': 'paper-aggressive'},
    {'pid': 22, 'account': 'paper-neutral'},
    {'pid': 23, 'account': 'paper-defensive'},
    {'pid': 24, 'account': 'paper-allweather'},
]

INTERVAL = 21 * 24 * 60 * 60  # 21 trading days in seconds
NOW = datetime.now(timezone.utc).isoformat()

connection.connect()
connection.client.sync()

with closing(connection.client.cursor()) as cur:
    cur.execute('DELETE FROM reconcile_jobs')
    for job in JOBS:
        cur.execute(
            '''INSERT INTO reconcile_jobs
               (PID, INTERVAL_SECONDS, METHOD, THRESHOLD, APPLY,
                EXECUTE_TRADES, DRY_RUN_TRADES, ENABLED, CREATED_AT, UPDATED_AT)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (job['pid'], INTERVAL, 'score_weighted', 0.05,
             1, 0, 1, 1, NOW, NOW),
        )
    connection.client.commit()
    connection.client.sync()

print(f'Seeded {len(JOBS)} reconcile jobs.')
