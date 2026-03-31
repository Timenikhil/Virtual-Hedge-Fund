import math, random
from datetime import date, timedelta
from contextlib import closing
from vhf.db import connection

strategies = {
    'strat-1': dict(start=1000, mu=0.18,  sigma=0.20, seed=1),  # Momentum: strong uptrend
    'strat-2': dict(start=1000, mu=0.04,  sigma=0.12, seed=2),  # Mean Reversion: low drift
    'strat-3': dict(start=1000, mu=0.10,  sigma=0.10, seed=3),  # Value: steady, low vol
    'strat-4': dict(start=1000, mu=0.06,  sigma=0.05, seed=4),  # Market Making: very stable
    'strat-5': dict(start=1000, mu=0.07,  sigma=0.09, seed=5),  # Pairs Trading: market neutral
    'strat-6': dict(start=1000, mu=0.14,  sigma=0.30, seed=6),  # Options: high vol
    'strat-7': dict(start=1000, mu=0.22,  sigma=0.25, seed=7),  # ML: highest alpha
    'strat-8': dict(start=1000, mu=0.08,  sigma=0.07, seed=8),  # Risk Parity: low vol
}

def gbm(start, mu, sigma, n, seed):
    rng = random.Random(seed)
    dt = 1 / 252
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * math.exp(
            (mu - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * rng.gauss(0, 1)
        ))
    return prices

def trading_days(n):
    days, d = [], date(2025, 1, 2)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days

dates = trading_days(252)
connection.connect()
connection.client.sync()

# Build all rows in memory first
all_rows = []
for sid, p in strategies.items():
    prices = gbm(p['start'], p['mu'], p['sigma'], 252, p['seed'])
    for i in range(252):
        all_rows.append((sid, dates[i], round(prices[i], 4)))
    ret = (prices[-1] / prices[0] - 1) * 100
    print(f'  {sid:12s}  {prices[0]:.2f} -> {prices[-1]:.2f}  ({ret:+.1f}%)')

# Single transaction
with closing(connection.client.cursor()) as cur:
    cur.execute('DELETE FROM strategy_price_history')
    cur.executemany(
        'INSERT INTO strategy_price_history (SID, TS, PRICE) VALUES (?, ?, ?)', all_rows
    )
    connection.client.commit()
    connection.client.sync()

print(f'\nDone. Inserted {len(all_rows)} rows.')
