"""
Shared static fixture data for unit tests.

Import directly in test files:

    from tests.fixtures import STRATEGIES, PORTFOLIOS, PRICE_POINTS, strategy_factory

No DB or network access required.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Raw strategy dicts  (match StrategyUpsertRequest / upsert_strategy kwargs)
# ---------------------------------------------------------------------------

STRATEGIES: list[dict[str, str]] = [
    {
        "strategy_id": "mom_us_large",
        "name": "US Large Cap Momentum",
        "description": "12-1 month price momentum on S&P 500 constituents",
        "category": "equity",
    },
    {
        "strategy_id": "mean_rev_us",
        "name": "US Equity Mean Reversion",
        "description": "Short-term RSI/z-score mean reversion on Russell 1000",
        "category": "equity",
    },
    {
        "strategy_id": "trend_intl",
        "name": "International Trend Following",
        "description": "200-day MA trend filter on MSCI EAFE country ETFs",
        "category": "equity",
    },
    {
        "strategy_id": "val_factor_us",
        "name": "US Value Factor",
        "description": "Composite value score on S&P 1500",
        "category": "equity",
    },
    {
        "strategy_id": "quality_factor",
        "name": "US Quality Factor",
        "description": "High ROE, low leverage, stable earnings growth on S&P 500",
        "category": "equity",
    },
    {
        "strategy_id": "low_vol_factor",
        "name": "Low Volatility Factor",
        "description": "Minimum variance portfolio on S&P 500",
        "category": "equity",
    },
    {
        "strategy_id": "sector_rotation",
        "name": "Sector Rotation",
        "description": "Relative strength rotation across 11 GICS sector ETFs",
        "category": "equity",
    },
    {
        "strategy_id": "rates_macro",
        "name": "Rates Macro",
        "description": "Duration-managed long/short Treasury strategy",
        "category": "fixed_income",
    },
    {
        "strategy_id": "credit_ls",
        "name": "Credit Long/Short",
        "description": "Long IG credit, short HY via index ETFs",
        "category": "alternatives",
    },
    {
        "strategy_id": "vol_arb",
        "name": "Volatility Arbitrage",
        "description": "VIX term-structure arbitrage",
        "category": "alternatives",
    },
]

STRATEGY_IDS: list[str] = [s["strategy_id"] for s in STRATEGIES]

# ---------------------------------------------------------------------------
# Sample price points  (ISO timestamp, price in cents)
# ---------------------------------------------------------------------------

# Short deterministic price series — enough for allocation / rebalance tests.
_BASE = 1000.0

PRICE_POINTS: dict[str, list[tuple[str, float]]] = {
    "mom_us_large": [
        ("2025-01-02", 1000.0), ("2025-01-03", 1015.2), ("2025-01-06", 1028.4),
        ("2025-01-07", 1041.9), ("2025-01-08", 1058.3), ("2025-01-09", 1072.1),
        ("2025-01-10", 1065.7), ("2025-01-13", 1079.4), ("2025-01-14", 1094.8),
        ("2025-01-15", 1110.3),
    ],
    "mean_rev_us": [
        ("2025-01-02", 1000.0), ("2025-01-03", 985.6), ("2025-01-06", 1002.1),
        ("2025-01-07", 988.3), ("2025-01-08", 1007.9), ("2025-01-09", 995.4),
        ("2025-01-10", 1012.7), ("2025-01-13", 998.2), ("2025-01-14", 1015.6),
        ("2025-01-15", 1003.1),
    ],
    "trend_intl": [
        ("2025-01-02", 1000.0), ("2025-01-03", 1008.3), ("2025-01-06", 1016.9),
        ("2025-01-07", 1025.8), ("2025-01-08", 1034.1), ("2025-01-09", 1042.7),
        ("2025-01-10", 1038.4), ("2025-01-13", 1047.2), ("2025-01-14", 1056.1),
        ("2025-01-15", 1065.3),
    ],
    "val_factor_us": [
        ("2025-01-02", 1000.0), ("2025-01-03", 1004.7), ("2025-01-06", 1009.5),
        ("2025-01-07", 1014.3), ("2025-01-08", 1019.2), ("2025-01-09", 1024.1),
        ("2025-01-10", 1021.8), ("2025-01-13", 1026.8), ("2025-01-14", 1031.9),
        ("2025-01-15", 1037.1),
    ],
    "quality_factor": [
        ("2025-01-02", 1000.0), ("2025-01-03", 1011.4), ("2025-01-06", 1023.1),
        ("2025-01-07", 1035.0), ("2025-01-08", 1047.2), ("2025-01-09", 1059.6),
        ("2025-01-10", 1053.9), ("2025-01-13", 1066.5), ("2025-01-14", 1079.4),
        ("2025-01-15", 1092.6),
    ],
}

# Strategies not in PRICE_POINTS have no history — tests can assert on that.

# ---------------------------------------------------------------------------
# Portfolio fixtures
# ---------------------------------------------------------------------------

PORTFOLIOS: list[dict[str, Any]] = [
    {
        "portfolio_name": "Alpha Fund",
        "account": "U1000001",
        "strategies": ["mom_us_large", "quality_factor", "val_factor_us", "sector_rotation", "trend_intl"],
    },
    {
        "portfolio_name": "Diversified Fund",
        "account": "U1000002",
        "strategies": STRATEGY_IDS,
    },
]

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def strategy_factory(**overrides: Any) -> dict[str, Any]:
    """Return a strategy dict with sensible defaults, optionally overridden."""
    defaults: dict[str, Any] = {
        "strategy_id": "test_strat",
        "name": "Test Strategy",
        "description": "A test strategy",
        "category": "equity",
    }
    defaults.update(overrides)
    return defaults


def price_points_factory(
    strategy_id: str,
    n: int = 5,
    start: float = 1000.0,
    step: float = 10.0,
) -> list[tuple[str, float]]:
    """Return a simple linear price series for testing."""
    from datetime import date, timedelta
    points: list[tuple[str, float]] = []
    day = date(2025, 1, 2)
    price = start
    count = 0
    while count < n:
        if day.weekday() < 5:
            points.append((day.isoformat(), round(price, 4)))
            price += step
            count += 1
        day += timedelta(days=1)
    return points


def allocation_context_factory(
    strategies: list[str] | None = None,
    prices: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Build a minimal AI allocation context dict for testing."""
    strats = strategies or ["mom_us_large", "quality_factor"]
    strat_prices = prices or {s: [1000.0, 1010.0, 1020.0] for s in strats}
    return {
        "portfolio_id": 1,
        "strategies": strats,
        "current_weights": [1.0 / len(strats)] * len(strats),
        "strategy_data": [
            {
                "strategy_id": s,
                "name": s,
                "description": "",
                "category": "equity",
                "prices": strat_prices.get(s, []),
                "latest_price": strat_prices.get(s, [0])[-1],
                "price_count": len(strat_prices.get(s, [])),
            }
            for s in strats
        ],
        "generated_at": "2025-01-15T12:00:00+00:00",
    }
