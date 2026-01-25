from enum import Enum
from typing import List

from pydantic import BaseModel


class Portfolio(BaseModel):
    portfolio_id: int
    portfolio_name: str
    weights: List[float] | None = None
    strategies: List[str] # ids of strategies
    live : bool = False

class PortfolioList(BaseModel):
    portfolios: List[Portfolio]

class PortfolioSelector(str,Enum):
    topk = "topk"
    bottomk = "bottomk"
    ai = "ai"  # allows ai to choose selection strategy

class PortfolioCreationRequest(BaseModel):
    portfolio_name: str
    strategies: List[str] # ids of strategies

class PortfolioID(BaseModel):
    portfolio_id: int

class PortfolioRequest(PortfolioID):
    strategies: List[str] # ids of strategies

class PortfolioWeights(PortfolioID):
    weights : List[float]

class PortfolioSelectorRequest(PortfolioID) :
    selector : PortfolioSelector | None = None,
    k:int = 10