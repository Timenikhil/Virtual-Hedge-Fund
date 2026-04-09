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


_POOL_SYSTEM_PROMPT = """\
You are a portfolio construction assistant. Given a list of available trading \
strategies and a natural language description of what the user wants, select the \
most appropriate strategies for the portfolio.

Return ONLY a JSON array of strategy_id strings from the provided list.
Do not invent strategy IDs. Only include IDs from the available list.
No explanation, no markdown. Only the JSON array.
Example: ["mom_us_large", "quality_factor"]
"""


def selectStrat(prompt: str | None, available_ids: list[str] | None = None) -> list[str]:
    """
    Use Claude to select strategy IDs from available_ids based on a natural language prompt.

    Falls back to returning all available_ids when the prompt is empty or Claude
    is unavailable. If available_ids is None, returns empty list.
    """
    if not prompt:
        return available_ids or []

    if not available_ids:
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("AI_WEIGHT_ALLOCATOR_MODEL", "claude-sonnet-4-6")

    try:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")

        pool_list = "\n".join(f"  - {sid}" for sid in available_ids)
        user_msg = (
            f"Available strategies:\n{pool_list}\n\n"
            f"User request: {prompt}\n\n"
            f"Return a JSON array of strategy_id strings to include in the portfolio."
        )

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=256,
            system=_POOL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        if not message.content:
            raise ValueError("Anthropic API returned empty content")

        response_text = message.content[0].text.strip()

        # Parse JSON array from the response.
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*?\]", response_text, re.DOTALL)
            if not match:
                raise ValueError(f"No JSON array in response: {response_text!r}")
            parsed = json.loads(match.group())

        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array")

        # Validate: only keep IDs that actually exist in available_ids.
        available_set = set(available_ids)
        selected = [str(sid) for sid in parsed if str(sid) in available_set]
        if not selected:
            logger.warning("selectStrat: Claude returned no valid strategy IDs; using all available")
            return available_ids

        return selected

    except Exception as exc:
        logger.warning("selectStrat: Claude call failed (%s); returning all available strategies", exc)
        return available_ids


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
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=64,
            system=_SELECTOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_selector_prompt(portfolioID, summaries)}],
        )
        if not message.content:
            raise ValueError("Anthropic API returned an empty content list")
        response_text = message.content[0].text
        return _parse_selector_response(response_text, n)
    except Exception as exc:
        logger.warning(
            "selectSelector: Claude call failed for portfolio %s (%s); using topk fallback",
            portfolioID, exc,
        )
        return PortfolioSelector.topk, min(DEFAULT_AI_SELECTOR_K, n)
