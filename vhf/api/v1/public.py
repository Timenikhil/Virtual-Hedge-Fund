import datetime
from typing import List

from fastapi import APIRouter, Path, HTTPException

from vhf.ai.ai_selectors import selectStrat, selectSelector
from vhf.ai.selectors import selectorStrat
from vhf.db.operations import set_db_pool, get_db_portfolio, update_portfolio_weights, update_portfolio_strats, \
    get_ranked_list, get_sids, get_db_portfolio_id, get_ranked_strat_list, get_db_strat
from vhf.models.error import HTTPError
from vhf.logging.log import logger
from vhf.models.portfolio import Portfolio, PortfolioList, \
    PortfolioSelectorRequest, PortfolioWeights, PortfolioCreationRequest, PortfolioRequest, PortfolioID
from vhf.models.strategy import StrategyID, StrategyPrice, StrategyList

router = APIRouter()

@router.post("/select-pool")
async def select_pool(pool : PortfolioCreationRequest) -> int:
    """
    Selects Strategy pool from all strategies
    :param pool:
    :return: Portfolio ID
    """
    print("here")
    return set_db_pool(pool,datetime.datetime.today().isoformat())

@router.post("/ai-select-pool")
async def select_pool(poolName : str, prompt : str | None = None) -> int:
    """
    Selects Strategy pool from all strategies
    :param poolName:
    :return: Portfolio ID
    """
    pool = PortfolioCreationRequest(portfolio_name=poolName, strategies = selectStrat(prompt))
    return set_db_pool(pool,datetime.datetime.today().isoformat())

@router.post("/ai-select-portfolio")
async def select_portfolio(pid: PortfolioID) -> List[str]:
    """
    Update portfolio using selector
    :param portfolioID:
    Ai selects the selector
    :return:
    """

    selector,k = selectSelector(pid.portfolio_id)
    strategies = selectorStrat(get_sids(pid.portfolio_id),selector,k)
    update_portfolio_strats(portfolioID=pid.portfolio_id,strats=strategies)
    return strategies

@router.post("/select-portfolio")
async def select_portfolio(portfolioReq : PortfolioSelectorRequest) -> List[str]:
    """
    Update portfolio using selector
    :param portfolioID:
    :param selector:
    :return:
    """
    strategies = selectorStrat(get_sids(portfolioReq.portfolio_id),portfolioReq.selector,portfolioReq.k)
    update_portfolio_strats(portfolioID=portfolioReq.portfolio_id,strats=strategies)
    return strategies

@router.post("/choose-portfolio")
async def choose_portfolio(portfolio : PortfolioRequest) -> None:
    """
    Manually select portfolio from portfolio Pool.
    Updates given portfolio.
    :param strategies: strategies from given pool
    :param portfolioID: portfolio ID
    :return:
    """
    update_portfolio_strats(portfolioID=portfolio.portfolio_id,strats=portfolio.strategies)

@router.post("/seed-portfolio")
async def seed_portfolio(portfolioWeights : PortfolioWeights) -> None:
    """
    seed portfolio with weights.
    If this function is not called AI autoseeds portfolio.
    :param portfolioID:
    :param weights:
    :return:
    """
    total = sum(portfolioWeights.weights)
    weights = [x/total for x in portfolioWeights.weights]
    update_portfolio_weights(portfolioWeights.portfolio_id, weights)

@router.get("/portfolios")
async def get_portfolios(rankBy : str|None = None,limit:int|None = None) -> PortfolioList:
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

@router.post("/portfolio_id")
async def get_portfolio(portfolio_id : PortfolioID) -> Portfolio:
    """
    Returns a portfolio with given id under current user
    :param portfolio:
    :return:
    """
    return get_db_portfolio_id(portfolio_id.portfolio_id)

@router.get("/strategies")
async def get_strategies(rankBy : str|None = None,limit:int|None = None) -> StrategyList:
    """
    Returns a list of strategies ranked by rankBy.
    :param limit: max number of portfolios to return
    :param rankBy:
    :return:
    """
    return get_ranked_strat_list(rankBy,limit)

@router.post("/strategy")
async def get_strategy(strategy : StrategyID) -> StrategyPrice:
    """
    Returns a strategy with given ID under current user
    :param strategy:
    :return:
    """
    return get_db_strat(strategy.strategy_id)



