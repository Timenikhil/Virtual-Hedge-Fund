from typing import List

from vhf.db.ranking import getTop, getBottom, getCorr, getMax
from vhf.models.portfolio import PortfolioSelector


def selectorStrat(sids:List[str],selector:PortfolioSelector,k,algo ="XAI") -> List[str]:
    match selector:
        case PortfolioSelector.top:
            return getTop(sids,algo,k)

        case PortfolioSelector.bottom:
            return getBottom(sids,algo,k)

        case PortfolioSelector.corr:
            return getCorr(sids,k)

        case PortfolioSelector.max:
            return getMax(sids,algo,k)

        case PortfolioSelector.ai | _:
            return sids