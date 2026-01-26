from __future__ import annotations

from vhf.quantrocket.cli import (
    QuantRocketCliError,
    moonshot_orders,
    moonshot_trade,
)


class QuantRocketError(RuntimeError):
    pass


def orders_csv_is_empty(csv_text: str) -> bool:
    """
    Heuristic: if CSV only has header row or is blank, treat as 'no orders'.
    """
    lines = [ln for ln in csv_text.splitlines() if ln.strip() != ""]
    return len(lines) <= 1  # typical Moonshot header then no rows


def generate_orders_csv(
    strategy: str, review_date: str | None = None, accounts: list[str] | None = None
) -> str:
    """
    Generate orders CSV via QuantRocket moonshot CLI.
    """
    try:
        return moonshot_orders(
            strategy=strategy, review_date=review_date, accounts=accounts
        )
    except QuantRocketCliError as exc:
        raise QuantRocketError(str(exc)) from exc


def trade_strategy_to_alpaca(
    strategy: str, review_date: str | None = None, accounts: list[str] | None = None
) -> dict:
    """
    One-shot pipeline: generate orders via moonshot CLI, then trade (blotter).
    If no orders, returns status 'no_orders'.
    """
    try:
        csv_orders = moonshot_orders(
            strategy=strategy, review_date=review_date, accounts=accounts
        )
        if orders_csv_is_empty(csv_orders):
            return {"status": "no_orders", "detail": "Moonshot produced no orders."}

        trade_output = moonshot_trade(
            strategy=strategy, review_date=review_date, accounts=accounts
        )
        return {
            "status": "submitted",
            "detail": trade_output.strip(),
            "rows": csv_orders.count("\n"),
        }
    except QuantRocketCliError as exc:
        raise QuantRocketError(str(exc)) from exc
