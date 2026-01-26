from enum import Enum
from typing import List

from pydantic import BaseModel


class StrategyID(BaseModel):
    strategy_id: str

class Strategy(StrategyID):
    name: str
    description: str
    category : str

class StrategyList(BaseModel):
    strategies: List[Strategy]

class StrategyPrice(Strategy):
    prices: List[int] # in cents



