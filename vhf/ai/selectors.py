from __future__ import annotations

from typing import List

from vhf.models.portfolio import PortfolioSelector

DEFAULT_SELECTION_K = 10


def selectorStrat(sids: List[str], selector: PortfolioSelector | None, k: int) -> List[str]:
    """Select a subset of strategy ids using simple deterministic selectors."""
    if not sids:
        return []

    try:
        safe_k = int(k)
    except (TypeError, ValueError):
        safe_k = DEFAULT_SELECTION_K

    if safe_k <= 0:
        safe_k = len(sids)
    safe_k = min(safe_k, len(sids))

    mode = selector or PortfolioSelector.topk

    if mode == PortfolioSelector.bottomk:
        return list(sids[-safe_k:])

    # `ai` currently falls back to deterministic top-k until an AI selector score feed is wired.
    return list(sids[:safe_k])
