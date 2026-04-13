import datetime
from typing import List

from fastapi import APIRouter, Path, HTTPException, Security, Depends

from vhf.ai.ai_selectors import selectStrat, selectSelector
from vhf.ai.selectors import selectorStrat
from vhf.allocators.scheduler import attach_scheduler
from vhf.authentication.authentication import get_current_user
from vhf.db.operations import set_db_pool, get_db_portfolio, update_portfolio_weights, update_portfolio_strats, \
    get_ranked_list, get_sids, get_db_portfolio_id, get_ranked_strat_list, get_db_strat, delete_db_portfolio_id, \
    set_db_allocator, get_secured_ranked_list
from vhf.models.error import HTTPError
from vhf.logging.log import logger
from vhf.models.portfolio import Portfolio, PortfolioList, \
    PortfolioSelectorRequest, PortfolioWeights, PortfolioCreationRequest, PortfolioRequest, PortfolioID, \
    PortfolioAllocator
from vhf.models.strategy import StrategyID, StrategyPrice, StrategyList
from pydantic import BaseModel

from vhf.models.user import FirebaseUser, UserRole

router = APIRouter(
    # dependencies= [Security(get_current_user)]
)


class AiPortfolioCreationRequest(BaseModel):
    portfolio_name: str
    account: str
    prompt: str | None = None

@router.post("/select-pool")
async def select_pool(pool: PortfolioCreationRequest,
                      # user : FirebaseUser = Depends(get_current_user)
                      ) -> int:
    """
    Selects Strategy pool from all strategies
    :param pool:
    :return: Portfolio ID
    """
    return set_db_pool(pool,datetime.datetime.today().isoformat())#user.user_id)

@router.post("/ai-select-pool")
async def ai_select_pool(req: AiPortfolioCreationRequest,
                         # user : FirebaseUser = Depends(get_current_user)
                         ) -> int:
    """
    Selects Strategy pool from all strategies
    :param poolName:
    :return: Portfolio ID
    """
    pool = PortfolioCreationRequest(
        portfolio_name=req.portfolio_name,
        account=req.account,
        strategies=selectStrat(req.prompt),
    )
    return set_db_pool(pool, datetime.datetime.today().isoformat())#user.user_id)

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
    strategies = selectorStrat(get_sids(portfolioReq.portfolio_id),portfolioReq.selector,portfolioReq.k,portfolioReq.ranker.value)
    update_portfolio_strats(portfolioID=portfolioReq.portfolio_id,strats=strategies)
    logger.debug(f"Portfolio {portfolioReq.portfolio_id}: selected via {portfolioReq.selector}",
                 extra={"PID" : str(portfolioReq.portfolio_id),
                 "Selector":str(portfolioReq.selector)})
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
    logger.debug(f"Portfolio {portfolio.portfolio_id}: chosen",
                 extra={"PID" : str(portfolio.portfolio_id)})

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
    logger.debug(f"Portfolio {portfolioWeights.portfolio_id}: seeded",
                extra={"PID" : str(portfolioWeights.portfolio_id)})

@router.get("/portfolios")
async def get_portfolios(rankBy : str|None = None,limit:int|None = None,
                         # user : FirebaseUser = Depends(get_current_user)
                         ) -> PortfolioList:
    """
    Returns a list of portfolios ranked by rankBy.
    :param limit: max number of portfolios to return
    :param rankBy:
    :return:
    """
    # if user.role != UserRole.PUBLIC:
    return get_ranked_list(rankBy,limit)
    # else:
    #     return get_secured_ranked_list(user.user_id,rankBy,limit)

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

@router.delete("/portfolio_id")
async def delete_portfolio(portfolio_id : PortfolioID) -> None:
    """
    Returns a portfolio with given id under current user
    :param portfolio:
    :return:
    """
    logger.info(f"Portfolio {portfolio_id.portfolio_id}: deleted",
                extra={"PID" : str(portfolio_id.portfolio_id)})
    return delete_db_portfolio_id(portfolio_id.portfolio_id)

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

@router.post("/select-allocator")
async def set_allocator(portfolio_alloc : PortfolioAllocator) -> None:
    """

    Updates portfolio DB with allocator

    if allocator is not Buy and Hold (None), set up scheduler

    """
    logger.info(f"Portfolio {portfolio_alloc.portfolio_id}: finalised",
                extra={"PID" : str(portfolio_alloc.portfolio_id)})
    if portfolio_alloc.allocator is not None:
        set_db_allocator(portfolio_alloc.portfolio_id,portfolio_alloc.allocator.value)
        attach_scheduler(portfolio_alloc.portfolio_id,portfolio_alloc.interval)

