"""
Seed script: populate the VHF database with demo strategies, price history,
and sample portfolios.

Usage:
    poetry run python scripts/seed.py              # seed everything
    poetry run python scripts/seed.py --dry-run    # show what would be seeded, no DB writes

Requires:
    DB_URL and DB_TOKEN environment variables (or a .env file at repo root).

The script is idempotent: re-running it will upsert existing records without
creating duplicates.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

STRATEGIES: list[dict] = [
    {
        "strategy_id": "mom_us_large",
        "name": "US Large Cap Momentum",
        "description": (
            "12-1 month price momentum on S&P 500 constituents with monthly rebalancing. "
            "Long top-decile, short bottom-decile by trailing return."
        ),
        "category": "equity",
        "annual_drift": 0.14,
        "annual_vol": 0.16,
    },
    {
        "strategy_id": "mean_rev_us",
        "name": "US Equity Mean Reversion",
        "description": (
            "Short-term RSI/z-score mean reversion on Russell 1000. "
            "Enters on 2-sigma oversold/overbought signals, 5-day holding period."
        ),
        "category": "equity",
        "annual_drift": 0.07,
        "annual_vol": 0.20,
    },
    {
        "strategy_id": "trend_intl",
        "name": "International Trend Following",
        "description": (
            "200-day moving average trend filter on MSCI EAFE country ETFs. "
            "Equal-weight long positions on countries above trend."
        ),
        "category": "equity",
        "annual_drift": 0.09,
        "annual_vol": 0.18,
    },
    {
        "strategy_id": "val_factor_us",
        "name": "US Value Factor",
        "description": (
            "Composite value score (P/B, P/E, EV/EBITDA) on S&P 1500. "
            "Rebalanced quarterly, equal-weight top quintile."
        ),
        "category": "equity",
        "annual_drift": 0.10,
        "annual_vol": 0.15,
    },
    {
        "strategy_id": "quality_factor",
        "name": "US Quality Factor",
        "description": (
            "High ROE, low leverage, stable earnings growth screen on S&P 500. "
            "Monthly rebalance, market-cap weighted."
        ),
        "category": "equity",
        "annual_drift": 0.13,
        "annual_vol": 0.13,
    },
    {
        "strategy_id": "low_vol_factor",
        "name": "Low Volatility Factor",
        "description": (
            "Minimum variance portfolio on S&P 500 using 252-day realised vol. "
            "Targets ex-ante portfolio volatility of 8%."
        ),
        "category": "equity",
        "annual_drift": 0.08,
        "annual_vol": 0.09,
    },
    {
        "strategy_id": "sector_rotation",
        "name": "Sector Rotation",
        "description": (
            "Relative strength rotation across 11 GICS sector ETFs. "
            "Top 3 sectors by 3-month momentum, equal-weighted, monthly rebalance."
        ),
        "category": "equity",
        "annual_drift": 0.11,
        "annual_vol": 0.17,
    },
    {
        "strategy_id": "rates_macro",
        "name": "Rates Macro",
        "description": (
            "Duration-managed long/short Treasury strategy driven by yield curve slope "
            "and Fed model signals. 2y/10y spread as primary signal."
        ),
        "category": "fixed_income",
        "annual_drift": 0.05,
        "annual_vol": 0.06,
    },
    {
        "strategy_id": "credit_ls",
        "name": "Credit Long/Short",
        "description": (
            "Long investment-grade credit, short high-yield via index ETFs. "
            "Position sizing based on credit spread z-scores."
        ),
        "category": "alternatives",
        "annual_drift": 0.08,
        "annual_vol": 0.10,
    },
    {
        "strategy_id": "vol_arb",
        "name": "Volatility Arbitrage",
        "description": (
            "VIX term-structure arbitrage: short front-month VIX futures when "
            "VIX futures curve is in contango above historical threshold."
        ),
        "category": "alternatives",
        "annual_drift": 0.10,
        "annual_vol": 0.25,
    },
]

# ---------------------------------------------------------------------------
# Sample portfolios
# ---------------------------------------------------------------------------

PORTFOLIOS: list[dict] = [
    {
        "portfolio_name": "Alpha Fund",
        "account": "U1000001",
        "strategies": [
            "mom_us_large",
            "quality_factor",
            "val_factor_us",
            "sector_rotation",
            "trend_intl",
        ],
        "description": "Equity-focused long/short with momentum and factor tilts.",
    },
    {
        "portfolio_name": "Diversified Fund",
        "account": "U1000002",
        "strategies": [s["strategy_id"] for s in STRATEGIES],
        "description": "Full cross-asset portfolio across all available strategies.",
    },
]

# ---------------------------------------------------------------------------
# GBM price generation
# ---------------------------------------------------------------------------

_TRADING_DAYS_PER_YEAR = 252
_BASE_PRICE_CENTS = 1000.0  # starting NAV: $10.00


def _generate_prices(
    annual_drift: float,
    annual_vol: float,
    n_days: int = _TRADING_DAYS_PER_YEAR,
    seed: int = 42,
    start: date | None = None,
) -> list[tuple[str, float]]:
    """
    Geometric Brownian Motion price path.
    Returns list of (ISO date string, price in cents) pairs for trading days only.
    """
    rng = random.Random(seed)
    dt = 1.0 / _TRADING_DAYS_PER_YEAR
    price = _BASE_PRICE_CENTS
    current = start or date(2025, 1, 2)  # first trading day of 2025

    points: list[tuple[str, float]] = []
    calendar_day = current
    trading_days_seen = 0

    while trading_days_seen < n_days:
        # Skip weekends.
        if calendar_day.weekday() < 5:
            z = rng.gauss(0, 1)
            price *= math.exp(
                (annual_drift - 0.5 * annual_vol ** 2) * dt
                + annual_vol * math.sqrt(dt) * z
            )
            points.append((calendar_day.isoformat(), round(price, 4)))
            trading_days_seen += 1
        calendar_day += timedelta(days=1)

    return points


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_strategies(dry_run: bool) -> None:
    from vhf.db.operations import upsert_strategy, record_strategy_price_points

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Seeding {len(STRATEGIES)} strategies...")

    for i, strat in enumerate(STRATEGIES):
        sid = strat["strategy_id"]
        if not dry_run:
            upsert_strategy(
                strategy_id=sid,
                name=strat["name"],
                description=strat["description"],
                category=strat["category"],
            )

        prices = _generate_prices(
            annual_drift=strat["annual_drift"],
            annual_vol=strat["annual_vol"],
            seed=i + 100,  # unique seed per strategy
        )

        if not dry_run:
            record_strategy_price_points(sid, prices)

        print(
            f"  {'(would seed)' if dry_run else '✓'} {sid:25s} "
            f"{len(prices)} price points  "
            f"start={prices[0][1]:.2f}c  end={prices[-1][1]:.2f}c"
        )


def _seed_portfolios(dry_run: bool) -> None:
    from vhf.db.operations import (
        get_db_portfolio,
        set_db_pool,
        update_portfolio_weights,
    )
    from vhf.models.portfolio import PortfolioCreationRequest
    from fastapi import HTTPException
    import datetime

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Seeding {len(PORTFOLIOS)} portfolios...")

    for portfolio in PORTFOLIOS:
        name = portfolio["portfolio_name"]
        strategies = portfolio["strategies"]
        n = len(strategies)
        equal_weights = [round(1.0 / n, 6)] * n

        if dry_run:
            print(f"  (would seed) {name!r}  strategies={strategies}  weights={equal_weights}")
            continue

        # Check if portfolio already exists; skip creation if it does.
        try:
            existing = get_db_portfolio(name)
            pid = existing.portfolio_id
            print(f"  ~ {name!r} already exists (pid={pid}), skipping creation")
        except HTTPException:
            req = PortfolioCreationRequest(
                portfolio_name=name,
                account=portfolio["account"],
                strategies=strategies,
            )
            pid = set_db_pool(req, datetime.date.today().isoformat())
            update_portfolio_weights(pid, equal_weights)
            print(
                f"  ✓ {name!r} created (pid={pid})  "
                f"strategies={strategies}  weights={equal_weights}"
            )


def _verify(dry_run: bool) -> None:
    if dry_run:
        print("\n[DRY RUN] Skipping verification.")
        return

    from vhf.db.operations import get_db_strat, get_ranked_list, get_ranked_strat_list

    print("\nVerifying seeded data...")

    strat_list = get_ranked_strat_list(None, None)
    seeded_ids = {s["strategy_id"] for s in STRATEGIES}
    found_ids = {s.strategy_id for s in strat_list.strategies}
    missing = seeded_ids - found_ids
    if missing:
        print(f"  ✗ Missing strategies: {missing}")
        sys.exit(1)
    print(f"  ✓ All {len(STRATEGIES)} strategies present in DB")

    # Spot-check price history on first strategy.
    first_sid = STRATEGIES[0]["strategy_id"]
    strat = get_db_strat(first_sid)
    if not strat.prices:
        print(f"  ✗ No price history for {first_sid}")
        sys.exit(1)
    print(f"  ✓ {first_sid} has {len(strat.prices)} price points (latest={strat.prices[-1]})")

    portfolio_list = get_ranked_list(None, None)
    seeded_names = {p["portfolio_name"] for p in PORTFOLIOS}
    found_names = {p.portfolio_name for p in portfolio_list.portfolios}
    missing_portfolios = seeded_names - found_names
    if missing_portfolios:
        print(f"  ✗ Missing portfolios: {missing_portfolios}")
        sys.exit(1)
    print(f"  ✓ All {len(PORTFOLIOS)} portfolios present in DB")

    print("\nSeed complete and verified.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the VHF database with demo data.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be seeded without writing to the database.",
    )
    args = parser.parse_args()

    if not args.dry_run:
        # Connect eagerly so misconfigured credentials fail fast.
        from vhf.db import connection
        connection.connect()
        connection.verify_connectivity()
        print("DB connection OK.")

    _seed_strategies(dry_run=args.dry_run)
    _seed_portfolios(dry_run=args.dry_run)
    _verify(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
