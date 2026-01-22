from typing import List

from fastapi import APIRouter, Path, HTTPException

from vhf.ai.ai_selectors import selectStrat
from vhf.db.operations import set_db_pool, get_db_portfolio, update_portfolio_weights, update_portfolio_strats, \
    get_ranked_list, get_sids
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
    return set_db_pool(pool)

@router.post("/ai-select-pool")
async def select_pool(poolName : str, prompt : str | None = None) -> int:
    """
    Selects Strategy pool from all strategies
    :param poolName:
    :return: Portfolio ID
    """
    pool = PortfolioRequest(portfolio_name=poolName, strategies = selectStrat(prompt))
    return set_db_pool(pool)

@router.post("/ai-select-portfolio")
async def select_portfolio(portfolioID : int) -> int:
    """
    Update portfolio using selector
    :param portfolioID:
    Ai selects the selector
    :return:
    """

    selector = selectSelector(portfolioID)
    strategies = selectorStrat(get_sids(portfolioID),selector)
    update_portfolio_strats(portfolioID=portfolioID,strats=strategies)

@router.post("/select-portfolio")
async def select_portfolio(portfolioID : int, selector : PortfolioSelector | None = None,k = 10) -> None:
    """
    Update portfolio using selector
    :param portfolioID:
    :param selector:
    :return:
    """
    strategies = selectorStrat(get_sids(portfolioID),selector)
    update_portfolio_strats(portfolioID=portfolioID,strats=strategies)

@router.post("/choose-portfolio")
async def choose_portfolio(portfolioID : int, strategies : List[str]) -> None:
    """
    Manually select portfolio from portfolio Pool.
    Updates given portfolio.
    :param strategies: strategies from given pool
    :param portfolioID: portfolio ID
    :return:
    """
    update_portfolio_strats(portfolioID=portfolioID,strats=strategies)

@router.post("/seed-portfolio")
async def seed_portfolio(portfolioID : int, weights : List[int]) -> None:
    """
    seed portfolio with weights.
    If this function is not called AI autoseeds portfolio.
    :param portfolioID:
    :param weights:
    :return:
    """
    total = sum(weights)
    weights = [x/total for x in weights]
    update_portfolio_weights(portfolioID, weights)

@router.get("/portfolios")
async def get_portfolios(rankBy : str,limit:int|None = None) -> PortfolioList:
    """
    Returns a list of portfolios ranked by rankBy.
    :param limit: max number of portfolios to return
    :param rankBy:
    :return:
    """
    return get_ranked_list(rankBy,limit)

@router.get("/portfolio")
async def get_portfolio(portfolioName : str) -> Portfolio:
    """
    Returns a portfolio with given name under current user
    :param portfolioName:
    :return:
    """
    return get_db_portfolio(portfolioName)