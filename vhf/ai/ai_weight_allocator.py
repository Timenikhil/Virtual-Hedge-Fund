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
trading strategies by analysing their risk-adjusted performance metrics and \
cross-strategy correlations.

WITHIN a single asset category (e.g. all equity strategies):
- Favour higher Sharpe ratio (prefer 2-year Sharpe over 1-year when both are provided)
- Favour stronger recent momentum (3-month, 1-year returns)
- Reduce weight in strategies with deep drawdowns relative to category peers

ACROSS asset categories (equity, fixed_income, alternatives):
- Treat low or negative correlation as a source of portfolio value, not a penalty.
  A bond or alternatives strategy with r < 0 vs equity provides drawdown protection \
even when its standalone return is lower.
- Do not eliminate an asset category solely because of recent underperformance — \
  this destroys diversification and increases portfolio tail risk.
- Maintain meaningful allocations (>10%) to each asset category present in the portfolio \
  unless a category has both negative Sharpe AND high positive correlation to all others.
- Weight reduction should be gradual: avoid concentrating >60% in a single category.

CLUSTER-AWARE ALLOCATION (HRP-inspired):
When strategy clusters are provided, apply a two-level approach: first allocate \
capital across clusters to maximise diversification (inter-cluster), then tilt \
within each cluster toward the strategy with the superior Sharpe ratio (intra-cluster). \
Each cluster is one diversification unit — do not concentrate more than its share in \
any single strategy unless it is the sole cluster member.

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
    correlation_matrix: list[list[float]] | None = context.get("correlation_matrix")
    strategy_clusters: dict[str, int] | None = context.get("strategy_clusters")
    request_context: dict | None = context.get("request_context")

    lines: list[str] = [
        f"Allocate across {len(strategies)} strategies. Performance metrics (daily prices, annualised where noted):\n",
        f"{'Strategy':<26} {'Category':<14} {'1M Ret':>8} {'3M Ret':>8} {'1Y Ret':>8} {'Cum Ret':>9} {'Vol63d':>7} {'Sh1Y':>6} {'Sh2Y':>6} {'MaxDD':>8} {'Calmar':>7} {'Mom':>6}",
        "-" * 127,
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
            f"{_fmt(m.get('sharpe_252d'), suffix='', plus=True):>6} "
            f"{_fmt(m.get('sharpe_504d'), suffix='', plus=True):>6} "
            f"{_fmt(m.get('max_drawdown_pct')):>8} "
            f"{_fmt(m.get('calmar_ratio'), suffix='', plus=True):>7} "
            f"{_fmt(m.get('momentum_ratio'), suffix='x', plus=True):>6}"
        )

    # Render correlation matrix as a lower-triangle table when available.
    # This gives the AI the cross-strategy diversification signal it needs for
    # cross-asset portfolios (bonds/alternatives have r < 0 vs equity).
    if correlation_matrix and len(correlation_matrix) == len(strategies):
        col_w = 7
        # Shorten labels to fit in column width
        short = [s[:col_w - 1] for s in strategies]
        lines.append(
            f"\nPairwise correlations (252-day daily returns) — "
            f"negative r = diversification hedge, positive r > 0.8 = high overlap:"
        )
        header = f"{'':26}" + "".join(f"{h:>{col_w}}" for h in short)
        lines.append(header)
        for i, sid in enumerate(strategies):
            row_vals = "".join(
                f"{correlation_matrix[i][j]:>{col_w}.2f}" if j <= i else " " * col_w
                for j in range(len(strategies))
            )
            lines.append(f"{sid:<26}{row_vals}")

    if strategy_clusters and len(strategy_clusters) == len(strategies):
        cluster_map: dict[int, list[str]] = {}
        for sid in strategies:
            label = strategy_clusters.get(sid)
            if label is not None:
                cluster_map.setdefault(label, []).append(sid)
        lines.append(
            "\nStrategy clusters (hierarchical clustering on 252-day return correlations, "
            "\u03c1 > 0.50 threshold):"
        )
        for label in sorted(cluster_map):
            lines.append(f"  Cluster {label + 1}: {', '.join(cluster_map[label])}")
        lines.append(
            "\nGuidance: Diversify capital across clusters (inter-cluster). "
            "Within each cluster, tilt toward the strategy with the better Sharpe ratio (intra-cluster)."
        )

    if current_weights and len(current_weights) == len(strategies):
        cw_str = ", ".join(f"{w:.3f}" for w in current_weights)
        lines.append(f"\nCurrent weights: [{cw_str}]")

    if request_context:
        lines.append(f"\nAdditional context: {json.dumps(request_context)}")

    retry_info: dict | None = context.get("_retry")
    if retry_info:
        lines.append(
            f"\n\u26a0 Retry attempt {retry_info['attempt']}. Your previous response could not be parsed:\n"
            f"  {retry_info['parse_error']}\n"
            f"{retry_info.get('hint', 'Respond with ONLY a JSON array of numbers. No explanation, no markdown, no extra text.')}"
        )

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
