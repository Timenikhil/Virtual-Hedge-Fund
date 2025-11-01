from __future__ import annotations
import os
import requests

DEFAULT_HOUSTON = "http://localhost:1969"
HOUSTON = os.getenv("HOUSTON_URL", DEFAULT_HOUSTON)


class QuantRocketError(RuntimeError):
    pass


def generate_orders_csv(
    strategy: str, review_date: str | None = None, accounts: list[str] | None = None
) -> str:
    """
    Calls GET /moonshot/orders.csv to generate orders for a strategy (or multiple).
    Returns CSV string (header + rows). Returns header-only if no orders.
    """
    params: dict[str, str] = {"strategies": strategy}
    if review_date:
        params["review_date"] = review_date
    if accounts:
        params["accounts"] = ",".join(accounts)
    try:
        r = requests.get(f"{HOUSTON}/moonshot/orders.csv", params=params, timeout=60)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        raise QuantRocketError(f"Failed to generate orders from Moonshot: {e}") from e


def place_orders_csv(csv_body: str) -> dict:
    """
    Sends CSV orders to POST /blotter/orders (routes to Alpaca if configured).
    Returns JSON response (e.g., list of order refs or status).
    """
    try:
        r = requests.post(
            f"{HOUSTON}/blotter/orders",
            headers={"Content-Type": "text/csv"},
            data=csv_body,
            timeout=60,
        )
        r.raise_for_status()
        # blotter often returns JSON (order refs); if not, surface text.
        try:
            return r.json()
        except ValueError:
            return {"result": r.text}
    except requests.RequestException as e:
        raise QuantRocketError(f"Failed to submit orders to blotter: {e}") from e


def orders_csv_is_empty(csv_text: str) -> bool:
    """
    Heuristic: if CSV only has header row or is blank, treat as 'no orders'.
    """
    lines = [ln for ln in csv_text.splitlines() if ln.strip() != ""]
    return len(lines) <= 1  # typical Moonshot header then no rows


def trade_strategy_to_alpaca(
    strategy: str, review_date: str | None = None, accounts: list[str] | None = None
) -> dict:
    """
    One-shot pipeline: generate orders -> (if any) submit to blotter.
    """
    csv_orders = generate_orders_csv(
        strategy=strategy, review_date=review_date, accounts=accounts
    )
    if orders_csv_is_empty(csv_orders):
        return {"status": "no_orders", "detail": "Moonshot produced no orders."}
    result = place_orders_csv(csv_orders)
    return {"status": "submitted", "detail": result, "rows": csv_orders.count("\n")}
