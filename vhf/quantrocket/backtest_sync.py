"""
Runs a QuantRocket Moonshot backtest by calling the houston API gateway
directly over HTTP (POST /moonshot/backtests), converts the daily Return
series to a cumulative price series indexed to 100, and stores the result
in strategy_price_history via record_strategy_price_points.

This approach avoids needing the docker CLI inside the vhf-api container —
houston is reachable at http://houston within the shared Docker network.

CSV format returned by houston:
    Field,Date,<strategy_code>
    Return,2018-01-02,0.00192...
    AbsExposure,2018-01-02,0.999...
    ...
"""

import csv
import io
import logging
import os

import requests

from vhf.db.operations import record_strategy_price_points

logger = logging.getLogger(__name__)

HOUSTON_URL = os.getenv("HOUSTON_URL", "http://houston")


class BacktestSyncError(RuntimeError):
    pass


def sync_strategy_backtest(
    strategy_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int:
    """
    Run a QR Moonshot backtest for *strategy_id* via the houston HTTP API,
    parse the Return rows, build a cumulative price series (index = 100 on
    day 0), and persist it.

    Returns the number of price points stored.
    Raises BacktestSyncError on any failure.
    """
    params: dict = {"strategies": strategy_id}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    logger.info("Requesting backtest from houston for '%s' (params=%s)", strategy_id, params)
    try:
        response = requests.post(
            f"{HOUSTON_URL}/moonshot/backtests.csv",
            params=params,
            timeout=60 * 60 * 24,
        )
        response.raise_for_status()
        csv_text = response.text
    except requests.RequestException as exc:
        raise BacktestSyncError(
            f"Houston request failed for strategy '{strategy_id}': {exc}"
        ) from exc

    logger.info(
        "Houston returned %d bytes for '%s'; parsing CSV",
        len(csv_text.encode()), strategy_id,
    )

    daily_returns: list[tuple[str, float]] = []
    try:
        reader = csv.reader(io.StringIO(csv_text))
        for row in reader:
            if len(row) < 3:
                continue
            field, date, value = row[0].strip(), row[1].strip(), row[2].strip()
            if field != "Return":
                continue
            try:
                daily_returns.append((date, float(value)))
            except ValueError:
                logger.debug("Skipping non-numeric Return value on %s: %r", date, value)
    except Exception as exc:
        raise BacktestSyncError(f"Failed to parse backtest CSV: {exc}") from exc

    logger.info("Parsed %d Return rows for '%s'", len(daily_returns), strategy_id)

    if not daily_returns:
        # Log first 500 chars of the response to diagnose unexpected formats
        logger.warning("No Return rows found. Response preview: %r", csv_text[:500])
        raise BacktestSyncError(
            f"No Return rows found in backtest output for strategy '{strategy_id}'. "
            "Ensure the strategy has been backtested and market data is loaded in QR."
        )

    daily_returns.sort(key=lambda x: x[0])

    # Drop leading zero-return rows (warm-up / no-data period at strategy start)
    first_active = next((i for i, (_, r) in enumerate(daily_returns) if r != 0.0), 0)
    daily_returns = daily_returns[first_active:]

    price = 100.0
    price_points: list[tuple[str, float]] = []
    for date, ret in daily_returns:
        price *= 1.0 + ret
        price_points.append((date, round(price, 6)))

    logger.info(
        "Writing %d price points for '%s' to DB (%s → %s)",
        len(price_points), strategy_id,
        price_points[0][0], price_points[-1][0],
    )
    record_strategy_price_points(strategy_id, price_points)
    logger.info("DB write complete for '%s'", strategy_id)
    return len(price_points)
