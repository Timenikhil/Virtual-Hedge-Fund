from typing import List

from vhf.models.portfolio import PortfolioSelector


def selectStrat(prompt) -> List[str]:
    return []

def selectSelector(portfolioID) -> PortfolioSelector:
    return "topk"