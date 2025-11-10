from enum import Enum
from typing import List

from pydantic import BaseModel


class Portfolio(BaseModel):
    portfolio_id: int
    portfolio_name: str
    strategies: List[int] # ids of strategies
    weights: List[float] | None = None
    live : bool = False

class PortfolioRequest(BaseModel):
    portfolio_name: str
    strategies: List[int] # ids of strategies

class PortfolioList(BaseModel):
    portfolios: List[Portfolio]

class PortfolioSelector(str,Enum):
    topk = "topk"
    bottomk = "bottomk"
    ai = "ai"  # allows ai to choose selection strategy
