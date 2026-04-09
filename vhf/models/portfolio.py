from enum import Enum
from typing import List

from pydantic import BaseModel

class PortfolioID(BaseModel):
    portfolio_id: int

class Portfolio(PortfolioID):
    portfolio_name: str
    weights: List[float] | None = None
    strategies: List[str] # ids of strategies
    live : bool = False
    date : str | None = None

class PortfolioList(BaseModel):
    portfolios: List[Portfolio]

class PortfolioSelector(str,Enum):
    topk = "topk"
    bottomk = "bottomk"
    ai = "ai"  # allows ai to choose selection strategy

class PortfolioCreationRequest(BaseModel):
    portfolio_name: str
    account: str
    strategies: List[str] # ids of strategies

class PortfolioRequest(PortfolioID):
    strategies: List[str] # ids of strategies

class PortfolioWeights(PortfolioID):
    weights : List[float]

class PortfolioSelectorRequest(PortfolioID) :
    selector : PortfolioSelector | None = None
    k:int = 10
