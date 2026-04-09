"""
seed_real.py — Seed the VHF database with REAL historical market data via yfinance.

Each strategy is proxied by a real ETF with a matching investment style.
Price history is fetched from Yahoo Finance and converted to a cumulative
return series (base = 1000.0 on the first available date), then stored in
strategy_price_history — the same table the backtest engine reads from.

Usage:
    poetry run python scripts/seed_real.py              # seed everything
    poetry run python scripts/seed_real.py --dry-run    # preview, no DB writes
    poetry run python scripts/seed_real.py --start-date 2010-01-01
    poetry run python scripts/seed_real.py --start-date 2005-01-01 --end-date 2025-12-31

Strategy → ETF proxy mapping (and rationale):
    mom_us_large    MTUM   iShares MSCI USA Momentum Factor ETF (US large-cap momentum)
    mean_rev_us     RSP    Invesco S&P 500 Equal Weight ETF (mean-reversion character)
    trend_intl      EFA    iShares MSCI EAFE ETF (international developed equity trend)
    val_factor_us   IVE    iShares S&P 500 Value ETF (US value factor)
    quality_factor  QUAL   iShares MSCI USA Quality Factor ETF (quality factor)
    low_vol_factor  USMV   iShares MSCI USA Min Vol Factor ETF (low volatility)
    sector_rotation XLK    Technology Select SPDR — strongest sector proxy
    rates_macro     TLT    iShares 20+ Year Treasury Bond ETF (rates/duration)
    credit_ls       LQD    iShares iBoxx $ Investment Grade Corporate Bond ETF
    vol_arb         SVXY   ProShares Short VIX Short-Term Futures ETF (short vol)

Notes:
  - MTUM and QUAL launched in 2013; earlier dates fall back to SPY and QQQ respectively.
  - SVXY had a reverse split in 2018; yfinance handles this via adjusted close prices.
  - All series are converted to cumulative returns (not raw price levels), so the
    absolute starting price is irrelevant — only return shape matters.
  - Dissertation framing: these are ETF proxies for strategy-style exposures,
    not the actual strategy NAVs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yfinance as yf

# ---------------------------------------------------------------------------
# Strategy → ETF mapping
# ---------------------------------------------------------------------------

STRATEGY_ETF_MAP: list[dict] = [
    {
        "strategy_id": "mom_us_large",
        "name": "US Large Cap Momentum",
        "description": (
            "12-1 month price momentum on S&P 500 constituents with monthly rebalancing. "
            "Proxied by MTUM (iShares MSCI USA Momentum Factor ETF)."
        ),
        "category": "equity",
        "ticker": "MTUM",
        "fallback_ticker": "SPY",   # MTUM launched Oct 2013
        "fallback_before": "2013-11-01",
    },
    {
        "strategy_id": "mean_rev_us",
        "name": "US Equity Mean Reversion",
        "description": (
            "Short-term RSI/z-score mean reversion on Russell 1000. "
            "Proxied by RSP (Invesco S&P 500 Equal Weight ETF)."
        ),
        "category": "equity",
        "ticker": "RSP",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "trend_intl",
        "name": "International Trend Following",
        "description": (
            "200-day moving average trend filter on MSCI EAFE country ETFs. "
            "Proxied by EFA (iShares MSCI EAFE ETF)."
        ),
        "category": "equity",
        "ticker": "EFA",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "val_factor_us",
        "name": "US Value Factor",
        "description": (
            "Composite value score (P/B, P/E, EV/EBITDA) on S&P 1500. "
            "Proxied by IVE (iShares S&P 500 Value ETF)."
        ),
        "category": "equity",
        "ticker": "IVE",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "quality_factor",
        "name": "US Quality Factor",
        "description": (
            "High ROE, low leverage, stable earnings growth screen on S&P 500. "
            "Proxied by QUAL (iShares MSCI USA Quality Factor ETF)."
        ),
        "category": "equity",
        "ticker": "QUAL",
        "fallback_ticker": "QQQ",   # QUAL launched Jul 2013
        "fallback_before": "2013-08-01",
    },
    {
        "strategy_id": "low_vol_factor",
        "name": "Low Volatility Factor",
        "description": (
            "Minimum variance portfolio on S&P 500 using 252-day realised vol. "
            "Proxied by USMV (iShares MSCI USA Min Vol Factor ETF)."
        ),
        "category": "equity",
        "ticker": "USMV",
        "fallback_ticker": "SPLV",
        "fallback_before": "2011-11-01",  # USMV launched Oct 2011
    },
    {
        "strategy_id": "sector_rotation",
        "name": "Sector Rotation",
        "description": (
            "Relative strength rotation across 11 GICS sector ETFs. "
            "Proxied by XLK (Technology Select Sector SPDR)."
        ),
        "category": "equity",
        "ticker": "XLK",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "rates_macro",
        "name": "Rates Macro",
        "description": (
            "Duration-managed long/short Treasury strategy driven by yield curve slope. "
            "Proxied by TLT (iShares 20+ Year Treasury Bond ETF)."
        ),
        "category": "fixed_income",
        "ticker": "TLT",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "credit_ls",
        "name": "Credit Long/Short",
        "description": (
            "Long investment-grade credit, short high-yield via index ETFs. "
            "Proxied by LQD (iShares iBoxx $ Investment Grade Corporate Bond ETF)."
        ),
        "category": "alternatives",
        "ticker": "LQD",
        "fallback_ticker": None,
        "fallback_before": None,
    },
    {
        "strategy_id": "vol_arb",
        "name": "Volatility Arbitrage",
        "description": (
            "VIX term-structure arbitrage: short front-month VIX futures when "
            "curve is in contango. Proxied by SVXY (ProShares Short VIX Short-Term Futures ETF)."
        ),
        "category": "alternatives",
        "ticker": "SVXY",
        "fallback_ticker": None,
        "fallback_before": "2011-10-04",  # SVXY launched Oct 2011
    },
]

PORTFOLIOS: list[dict] = [
    {
        "portfolio_name": "Alpha Fund",
        "account": "U1000001",
        "strategies": ["mom_us_large", "quality_factor", "val_factor_us", "sector_rotation", "trend_intl"],
    },
    {
        "portfolio_name": "Diversified Fund",
        "account": "U1000002",
        "strategies": [s["strategy_id"] for s in STRATEGY_ETF_MAP],
    },
]

_BASE_PRICE = 1000.0


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_prices(
    ticker: str,
    start: str,
    end: str,
) -> list[tuple[str, float]]:
    """
    Download adjusted close prices from Yahoo Finance and return as
    (ISO date, cumulative price) pairs indexed to _BASE_PRICE on day 0.
    """
    data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if data.empty:
        return []

    closes = data["Close"].dropna()
    if hasattr(closes, "squeeze"):
        closes = closes.squeeze()

    if closes.empty or len(closes) < 2:
        return []

    # Convert to cumulative return series (base = _BASE_PRICE)
    returns = closes.pct_change().fillna(0)
    cumulative = (1 + returns).cumprod() * _BASE_PRICE

    points: list[tuple[str, float]] = []
    for ts, price in zip(cumulative.index, cumulative.values):
        day_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        points.append((day_str, round(float(price), 4)))

    return points


def _get_price_points(
    strat: dict,
    start: str,
    end: str,
    dry_run: bool,
) -> list[tuple[str, float]]:
    """
    Fetch prices for a strategy, stitching fallback ticker for early dates if needed.
    """
    ticker = strat["ticker"]
    fallback = strat.get("fallback_ticker")
    fallback_before = strat.get("fallback_before")

    if fallback and fallback_before and start < fallback_before:
        # Fetch fallback for early period, primary for remainder
        early = _fetch_prices(fallback, start, fallback_before)
        late = _fetch_prices(ticker, fallback_before, end)

        if not early and not late:
            return []
        if not early:
            points = late
        elif not late:
            points = early
        else:
            # Re-index late series so it continues from where early left off
            last_early_price = early[-1][1]
            first_late_price = late[0][1]
            scale = last_early_price / first_late_price if first_late_price else 1.0
            late_scaled = [(d, round(p * scale, 4)) for d, p in late]
            points = early + late_scaled[1:]  # skip first late point (overlap)
    else:
        points = _fetch_prices(ticker, start, end)

    if not dry_run and not points:
        print(f"  ✗ No data returned for {ticker} ({strat['strategy_id']})")

    return points


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def _seed_strategies(start: str, end: str, dry_run: bool) -> None:
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Fetching real price data for {len(STRATEGY_ETF_MAP)} strategies...")
    print(f"  Date range: {start} → {end}\n")

    if not dry_run:
        from vhf.db.operations import upsert_strategy, record_strategy_price_points

    for strat in STRATEGY_ETF_MAP:
        sid = strat["strategy_id"]
        ticker = strat["ticker"]
        fallback = strat.get("fallback_ticker")
        ticker_label = f"{fallback}+{ticker}" if fallback and strat.get("fallback_before") and start < strat["fallback_before"] else ticker

        points = _get_price_points(strat, start, end, dry_run)

        if not dry_run:
            upsert_strategy(
                strategy_id=sid,
                name=strat["name"],
                description=strat["description"],
                category=strat["category"],
            )
            if points:
                record_strategy_price_points(sid, points)

        if points:
            print(
                f"  {'(would seed)' if dry_run else '✓'} {sid:25s}  [{ticker_label:10s}]  "
                f"{len(points):5d} pts  {points[0][0]} → {points[-1][0]}"
            )
        else:
            print(f"  {'(would skip)' if dry_run else '✗'} {sid:25s}  [{ticker_label:10s}]  no data")


def _seed_portfolios(dry_run: bool) -> None:
    from vhf.db.operations import get_db_portfolio, set_db_pool, update_portfolio_weights
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
            print(f"  (would seed) {name!r}  strategies={strategies}")
            continue

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
            print(f"  ✓ {name!r} created (pid={pid})")


def _verify(dry_run: bool) -> None:
    if dry_run:
        print("\n[DRY RUN] Skipping DB verification.")
        return

    from vhf.db.operations import get_strategy_price_history_raw

    print("\nVerifying loaded data...")
    all_ok = True
    for strat in STRATEGY_ETF_MAP:
        sid = strat["strategy_id"]
        pts = get_strategy_price_history_raw(sid)
        if pts:
            print(f"  ✓ {sid:25s}  {len(pts):5d} pts  {pts[0][0]} → {pts[-1][0]}")
        else:
            print(f"  ✗ {sid:25s}  NO DATA")
            all_ok = False

    if all_ok:
        print("\nAll strategies seeded with real market data.")
    else:
        print("\nSome strategies missing data — check ticker availability for the requested date range.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed VHF DB with real Yahoo Finance market data."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched/seeded without writing to DB.",
    )
    parser.add_argument(
        "--start-date",
        default="2005-01-01",
        help="Start date for historical data (default: 2005-01-01).",
    )
    parser.add_argument(
        "--end-date",
        default=date.today().isoformat(),
        help="End date for historical data (default: today).",
    )
    args = parser.parse_args()

    if not args.dry_run:
        from vhf.db import connection
        connection.connect()
        connection.verify_connectivity()
        print("DB connection OK.")

    _seed_strategies(args.start_date, args.end_date, args.dry_run)

    if not args.dry_run:
        _seed_portfolios(args.dry_run)
        _verify(args.dry_run)
    else:
        _seed_portfolios(args.dry_run)
        print("\n[DRY RUN] Complete. Re-run without --dry-run to write to DB.")


if __name__ == "__main__":
    main()
