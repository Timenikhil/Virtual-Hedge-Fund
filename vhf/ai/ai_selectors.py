from __future__ import annotations

import json
import math
import os
import re
from typing import List

import anthropic

from vhf.logging.log import logger
from vhf.models.portfolio import PortfolioSelector

DEFAULT_AI_SELECTOR_K = 10
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./-]+")

_SELECTOR_SYSTEM_PROMPT = """\
You are a quantitative portfolio strategist. Given a portfolio's strategy \
performance data, decide how to select a subset for trading.

Return ONLY a JSON object with two keys:
  "selector": one of "topk" (momentum — keep best performers) or \
"bottomk" (contrarian — keep worst performers)
  "k": an integer between 1 and the total number of strategies

No explanation, no markdown. Only the JSON object.
Example: {"selector": "topk", "k": 5}
"""


def selectStrat(prompt: str | None) -> List[str]:
    """
    Lightweight parser for strategy IDs from free-form prompt text.
    This keeps AI pool creation usable while the full LLM selector pipeline is external.
    """
    if not prompt:
        return []

    seen: set[str] = set()
    ordered: list[str] = []
    for token in TOKEN_PATTERN.findall(prompt):
        strategy_id = token.strip()
        if strategy_id == "" or strategy_id in seen:
            continue
        seen.add(strategy_id)
        ordered.append(strategy_id)

    return ordered


def _momentum(prices: list[float]) -> float:
    """Simple end-to-end return over the available price history."""
    if len(prices) < 2 or prices[0] == 0:
        return 0.0
    return (prices[-1] - prices[0]) / prices[0]


def _build_selector_prompt(portfolio_id: int, strategy_summaries: list[dict]) -> str:
    n = len(strategy_summaries)
    lines = [f"Portfolio {portfolio_id} has {n} strategies:"]
    for s in strategy_summaries:
        mom = s.get("momentum_pct", 0.0)
        lines.append(
            f"  - {s['strategy_id']} ({s.get('name', '?')}): "
            f"momentum {mom:+.1f}%, {s.get('price_count', 0)} price points"
        )
    lines.append(f"\nChoose a selector and k (1–{n}) to form an active sub-portfolio.")
    return "\n".join(lines)


def _parse_selector_response(text: str, n: int) -> tuple[PortfolioSelector, int]:
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^}]+\}", text)
        if not match:
            raise ValueError(f"No JSON object in response: {text!r}")
        parsed = json.loads(match.group())

    raw_selector = str(parsed.get("selector", "topk")).lower()
    selector = PortfolioSelector.bottomk if raw_selector == "bottomk" else PortfolioSelector.topk

    try:
        k = max(1, min(int(parsed.get("k", DEFAULT_AI_SELECTOR_K)), n))
    except (TypeError, ValueError):
        k = min(DEFAULT_AI_SELECTOR_K, n)

    return selector, k


def selectSelector(portfolioID: int) -> tuple[PortfolioSelector, int]:
    """
    Use Claude to decide which selector strategy (topk / bottomk) and k value
    to apply when trimming the portfolio's strategy pool.

    Falls back to (topk, DEFAULT_AI_SELECTOR_K) if the portfolio has no price
    data or if the Claude call fails.
    """
    # Import here to avoid circular imports at module load time.
    from vhf.db.operations import get_db_portfolio_id, get_db_strat

    try:
        portfolio = get_db_portfolio_id(portfolioID)
    except Exception as exc:
        logger.warning("selectSelector: could not load portfolio %s: %s", portfolioID, exc)
        return PortfolioSelector.topk, DEFAULT_AI_SELECTOR_K

    strategies = portfolio.strategies
    n = len(strategies)
    if n == 0:
        return PortfolioSelector.topk, DEFAULT_AI_SELECTOR_K

    summaries: list[dict] = []
    for sid in strategies:
        try:
            strat = get_db_strat(sid)
            prices = [float(p) for p in strat.prices if p is not None and math.isfinite(float(p))]
            summaries.append({
                "strategy_id": sid,
                "name": strat.name,
                "price_count": len(prices),
                "momentum_pct": _momentum(prices) * 100,
            })
        except Exception:
            summaries.append({"strategy_id": sid, "name": sid, "price_count": 0, "momentum_pct": 0.0})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("AI_WEIGHT_ALLOCATOR_MODEL", "claude-sonnet-4-6")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=64,
            system=_SELECTOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_selector_prompt(portfolioID, summaries)}],
        )
        response_text = message.content[0].text if message.content else ""
        return _parse_selector_response(response_text, n)
    except Exception as exc:
        logger.warning(
            "selectSelector: Claude call failed for portfolio %s (%s); using topk fallback",
            portfolioID, exc,
        )
        return PortfolioSelector.topk, min(DEFAULT_AI_SELECTOR_K, n)
