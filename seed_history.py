"""
Seed allocation and rebalance history for all 4 portfolios.
Uses actual GBM price data to compute realistic score_weighted snapshots
at monthly (21 trading day) intervals over the full price history.
"""
import json
from contextlib import closing
from vhf.db import connection

PORTFOLIOS = {
    21: {'name': 'Aggressive Growth',       'account': 'paper-aggressive', 'strategies': ['strat-1', 'strat-7', 'strat-6']},
    22: {'name': 'Market Neutral',           'account': 'paper-neutral',    'strategies': ['strat-5', 'strat-2', 'strat-4']},
    23: {'name': 'Defensive Income',         'account': 'paper-defensive',  'strategies': ['strat-8', 'strat-3', 'strat-2']},
    24: {'name': 'All-Weather Diversified',  'account': 'paper-allweather', 'strategies': ['strat-1','strat-2','strat-3','strat-4','strat-5','strat-6','strat-7','strat-8']},
}

connection.connect()
connection.client.sync()

# Load all price history
with closing(connection.client.cursor()) as cur:
    cur.execute('SELECT SID, TS, PRICE FROM strategy_price_history ORDER BY SID, TS')
    rows = cur.fetchall()

prices: dict[str, dict[str, float]] = {}
for sid, ts, price in rows:
    prices.setdefault(sid, {})[ts] = float(price)

all_dates = sorted({ts for p in prices.values() for ts in p})
rebalance_indices = list(range(21, len(all_dates), 21))  # monthly, skip day 0


def score_weights(strats: list[str], up_to_idx: int) -> list[float]:
    scores = []
    for sid in strats:
        hist = [prices.get(sid, {}).get(all_dates[j], 1000.0) for j in range(up_to_idx + 1)]
        if len(hist) >= 2 and hist[0] > 0:
            scores.append(max(hist[-1] / hist[0], 0.01))
        else:
            scores.append(1.0)
    total = sum(scores)
    return [s / total for s in scores]


def serialize(vals: list[float]) -> str:
    return ','.join(f'{v:.6f}' for v in vals)


with closing(connection.client.cursor()) as cur:
    cur.execute('DELETE FROM portfolio_allocations')
    cur.execute('DELETE FROM rebalance_runs')
    connection.client.commit()

    for pid, info in PORTFOLIOS.items():
        strats = info['strategies']
        n = len(strats)
        prev_weights = [1.0 / n] * n

        for idx in rebalance_indices:
            ts = all_dates[idx] + 'T09:30:00'
            new_weights = score_weights(strats, idx)
            trade_weights = [new_weights[i] - prev_weights[i] for i in range(n)]

            cur.execute(
                '''INSERT INTO portfolio_allocations
                   (PID, METHOD, STRATEGIES, RAW_WEIGHTS, TARGET_WEIGHTS, META, CREATED_AT)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (pid, 'score_weighted', ','.join(strats),
                 serialize(prev_weights), serialize(new_weights), '{}', ts),
            )
            cur.execute(
                '''INSERT INTO rebalance_runs
                   (PID, ACCOUNT, METHOD, THRESHOLD, STRATEGIES,
                    CURRENT_WEIGHTS, TARGET_WEIGHTS, TRADE_WEIGHTS, STATUS, META, CREATED_AT)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (pid, info['account'], 'score_weighted', 0.05, ','.join(strats),
                 serialize(prev_weights), serialize(new_weights), serialize(trade_weights),
                 'success', '{}', ts),
            )
            prev_weights = new_weights

        connection.client.commit()
        print(f'  {info["name"]}: {len(rebalance_indices)} snapshots seeded')

connection.client.sync()
print(f'Done. {len(PORTFOLIOS) * len(rebalance_indices)} allocation + rebalance rows inserted.')
