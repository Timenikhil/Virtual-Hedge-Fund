from typing import List

from fastapi import APIRouter, Path, HTTPException
from vhf.models.error import HTTPError
from vhf.logging.log import logger
from vhf.models.portfolio import Portfolio, PortfolioList, PortfolioRequest, PortfolioSelector

router = APIRouter()

@router.post("/select-pool")
async def select_pool(pool : PortfolioRequest) -> int:
    """
    Selects Strategy pool from all strategies
    :param pool:
    :return: Portfolio ID
    """
    return -1

@router.post("/ai-select-pool")
async def select_pool(poolName : str, prompt : str | None = None) -> int:
    """
    Selects Strategy pool from all strategies
    :param poolName:
    :return: Portfolio ID
    """
    return -1

@router.post("/ai-select-portfolio")
async def select_portfolio(portfolioID : int) -> int:
    """
    Update portfolio using selector
    :param portfolioID:
    Ai selects the selector
    :return:
    """
    return portfolioID

@router.post("/select-portfolio")
async def select_portfolio(portfolioID : int, selector : PortfolioSelector | None = None) -> int:
    """
    Update portfolio using selector
    :param portfolioID:
    :param selector:
    :return:
    """
    if selector is not None:
        pass
    return portfolioID

@router.post("/choose-portfolio")
async def choose_portfolio(portfolioID : int, strategies : List[int]) -> int:
    """
    Manually select portfolio from portfolio Pool.
    Updates given portfolio.
    :param portfolioID:
    :return:
    """
    return portfolioID

@router.post("/seed-portfolio")
async def seed_portfolio(portfolioID : int, weights : List[int]) -> None:
    """
    seed portfolio with weights.
    If this function is not called AI autoseeds portfolio.
    :param portfolioID:
    :param weights:
    :return:
    """
    return portfolioID



@router.get("/portfolios")
async def get_portfolios(rankBy : str) -> PortfolioList:
    """
    Returns a list of portfolios ranked by rankBy.
    :param rankBy:
    :return:
    """
    return PortfolioList()

@router.get("/portfolio")
async def get_portfolio(portfolioName : str) -> Portfolio:
    """
    Returns a portfolio with given name under current user
    :param portfolioName:
    :return:
    """
    return Portfolio()