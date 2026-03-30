from __future__ import annotations

import math
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

    if mode == PortfolioSelector.ai:
        # Score strategies by end-to-end price momentum; return top-k by score.
        # Import here to avoid circular imports at module load time.
        from vhf.db.operations import get_db_strat
        scored: list[tuple[float, str]] = []
        for sid in sids:
            try:
                strat = get_db_strat(sid)
                prices = [float(p) for p in strat.prices if p is not None and math.isfinite(float(p))]
                if len(prices) >= 2 and prices[0] != 0:
                    momentum = (prices[-1] - prices[0]) / prices[0]
                else:
                    momentum = 0.0
            except Exception:
                momentum = 0.0
            scored.append((momentum, sid))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [sid for _, sid in scored[:safe_k]]

    # topk: preserve original ordering, take first k.
    return list(sids[:safe_k])
