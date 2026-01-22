from enum import Enum
from typing import List

from pydantic import BaseModel


class Portfolio(BaseModel):
    portfolio_id: int
    portfolio_name: str
    weights: List[float] | None = None
    strategies: List[str] # ids of strategies
    live : bool = False

class PortfolioRequest(BaseModel):
    portfolio_name: str
    strategies: List[str] # ids of strategies

class PortfolioList(BaseModel):
    portfolios: List[Portfolio]

class PortfolioSelector(str,Enum):
    topk = "topk"
    bottomk = "bottomk"
    ai = "ai"  # allows ai to choose selection strategy
