"""
Local AI weight allocator using the Anthropic Claude API.

This module is the default implementation for AI_ALLOCATOR_MODE=local.
It receives a portfolio context dict and returns a list of weights,
one per strategy, which are then normalised by the allocation service.

Required env var:
    ANTHROPIC_API_KEY  – Anthropic API key

Optional env var:
    AI_WEIGHT_ALLOCATOR_MODEL  – Claude model to use (default: claude-sonnet-4-6)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 512

_SYSTEM_PROMPT = """\
You are a quantitative portfolio manager. Allocate capital across algorithmic \
trading strategies by analysing their risk-adjusted performance metrics.

Favour strategies with:
- Higher Sharpe ratio (risk-adjusted return)
- Stronger recent momentum (1-month, 3-month, 1-year returns)
- Lower drawdown for their return level

Reduce weight in strategies with poor risk-adjusted returns or deep drawdowns \
relative to peers. Diversify across asset categories when possible.

Rules:
- Return ONLY a JSON array of weights, one per strategy, in the same order as the input.
- All weights must be non-negative numbers.
- Weights do not need to sum to 1 — the caller will normalise them.
- Do not include any explanation, markdown, or extra text. Only the JSON array.
"""


def _fmt(val: float | None, suffix: str = "%", plus: bool = False) -> str:
    if val is None:
        return "n/a"
    sign = "+" if plus and val > 0 else ""
    return f"{sign}{val:.2f}{suffix}"


def _build_prompt(context: dict[str, Any]) -> str:
    strategies: list[str] = context.get("strategies", [])
    strategy_data: list[dict] = context.get("strategy_data", [])
    current_weights: list[float] | None = context.get("current_weights")
    request_context: dict | None = context.get("request_context")

    lines: list[str] = [
        f"Allocate across {len(strategies)} strategies. Performance metrics (daily prices, annualised where noted):\n",
        f"{'Strategy':<26} {'Category':<14} {'1M Ret':>8} {'3M Ret':>8} {'1Y Ret':>8} {'Cum Ret':>9} {'Vol63d':>7} {'Sharpe1Y':>9} {'MaxDD':>8}",
        "-" * 105,
    ]

    for sd in strategy_data:
        m = sd.get("metrics", {})
        lines.append(
            f"{sd.get('strategy_id', '?'):<26} "
            f"{sd.get('category', ''):<14} "
            f"{_fmt(m.get('return_20d_pct'),  plus=True):>8} "
            f"{_fmt(m.get('return_63d_pct'),  plus=True):>8} "
            f"{_fmt(m.get('return_252d_pct'), plus=True):>8} "
            f"{_fmt(m.get('return_cum_pct'),  plus=True):>9} "
            f"{_fmt(m.get('vol_63d_ann_pct')):>7} "
            f"{_fmt(m.get('sharpe_252d'), suffix='', plus=True):>9} "
            f"{_fmt(m.get('max_drawdown_pct')):>8}"
        )

    if current_weights and len(current_weights) == len(strategies):
        cw_str = ", ".join(f"{w:.3f}" for w in current_weights)
        lines.append(f"\nCurrent weights: [{cw_str}]")

    if request_context:
        lines.append(f"\nAdditional context: {json.dumps(request_context)}")

    lines.append(f"\nReturn a JSON array of exactly {len(strategies)} non-negative weights.")

    return "\n".join(lines)


def _parse_weights(text: str, expected_len: int) -> list[float]:
    """Extract the first JSON array from the model response."""
    text = text.strip()

    # Try direct parse first (model returned only the array).
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) == expected_len:
            return [float(v) for v in parsed]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fall back to regex extraction.
    match = re.search(r"\[[\d.,\s\-eE]+\]", text)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list) and len(parsed) == expected_len:
                return [float(v) for v in parsed]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    raise ValueError(
        f"Could not parse {expected_len} weights from model response: {text!r}"
    )


def allocate_weights(context: dict[str, Any]) -> list[float]:
    """
    Call Claude to produce a weight vector for the given portfolio context.

    Args:
        context: Portfolio context dict as built by allocation_service._build_ai_context().

    Returns:
        List of raw (un-normalised) weights, one per strategy.

    Raises:
        ValueError: If the model response cannot be parsed into a valid weight vector.
        anthropic.APIError: On API communication failures.
    """
    strategies: list[str] = context.get("strategies", [])
    if not strategies:
        raise ValueError("Context contains no strategies to allocate.")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Configure it or set AI_ALLOCATOR_MODE=disabled."
        )
    model = os.getenv("AI_WEIGHT_ALLOCATOR_MODEL", DEFAULT_MODEL)

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = _build_prompt(context)

    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    if not message.content:
        raise ValueError("Anthropic API returned an empty content list.")
    response_text = message.content[0].text
    return _parse_weights(response_text, len(strategies))
