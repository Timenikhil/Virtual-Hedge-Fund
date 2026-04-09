import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vhf.ai.ai_selectors import selectSelector, selectStrat
from vhf.ai.selectors import selectorStrat
from vhf.db.operations import (
    get_db_portfolio,
    get_db_portfolio_id,
    get_db_strat,
    get_portfolios_summary,
    get_ranked_list,
    get_ranked_strat_list,
    get_sids,
    set_db_pool,
    update_portfolio_strats,
    update_portfolio_weights,
)
from vhf.models.allocation import AllocationRequest, AllocationResult
from vhf.models.portfolio import (
    Portfolio,
    PortfolioCreationRequest,
    PortfolioID,
    PortfolioList,
    PortfolioRequest,
    PortfolioSelectorRequest,
    PortfolioWeights,
)
from vhf.models.rebalance import RebalancePlan, RebalanceRequest
from vhf.models.strategy import StrategyID, StrategyList, StrategyPrice
from vhf.services.allocation_service import AllocationServiceError, allocate_portfolio
from vhf.services.rebalance_engine import RebalanceEngineError, build_rebalance_plan


router = APIRouter()


class AiPortfolioCreationRequest(BaseModel):
    portfolio_name: str
    account: str
    prompt: str | None = None


@router.post("/select-pool")
async def select_pool(pool: PortfolioCreationRequest) -> int:
    """
    Select strategy pool from all strategies.
    """
    return set_db_pool(pool, datetime.datetime.today().isoformat())


@router.post("/ai-select-pool")
async def ai_select_pool(req: AiPortfolioCreationRequest) -> int:
    """
    Select strategy pool from all available strategies via Claude AI.
    Claude reads the prompt and chooses which strategies to include.
    Falls back to all strategies if the prompt is empty or Claude is unavailable.
    """
    all_strategies = get_ranked_strat_list(None, None)
    available_ids = [s.strategy_id for s in all_strategies.strategies]
    selected = selectStrat(req.prompt, available_ids)
    pool = PortfolioCreationRequest(
        portfolio_name=req.portfolio_name,
        account=req.account,
        strategies=selected,
    )
    return set_db_pool(pool, datetime.datetime.today().isoformat())


@router.post("/ai-select-portfolio")
async def ai_select_portfolio(pid: PortfolioID) -> List[str]:
    """
    Update portfolio strategies using AI-selected selector logic.
    """
    selector, k = selectSelector(pid.portfolio_id)
    strategies = selectorStrat(get_sids(pid.portfolio_id), selector, k)
    update_portfolio_strats(portfolioID=pid.portfolio_id, strats=strategies)
    return strategies


@router.post("/select-portfolio")
async def select_portfolio(portfolioReq: PortfolioSelectorRequest) -> List[str]:
    """
    Update portfolio strategies using explicit selector and k.
    """
    strategies = selectorStrat(get_sids(portfolioReq.portfolio_id), portfolioReq.selector, portfolioReq.k)
    update_portfolio_strats(portfolioID=portfolioReq.portfolio_id, strats=strategies)
    return strategies


@router.post("/choose-portfolio")
async def choose_portfolio(portfolio: PortfolioRequest) -> None:
    """
    Manually set strategies for a portfolio.
    """
    update_portfolio_strats(portfolioID=portfolio.portfolio_id, strats=portfolio.strategies)


@router.post("/seed-portfolio")
async def seed_portfolio(portfolioWeights: PortfolioWeights) -> None:
    """
    Seed portfolio with normalized weights.
    """
    total = sum(portfolioWeights.weights)
    if total <= 0:
        raise HTTPException(status_code=400, detail="weights must sum to a positive number")
    weights = [x / total for x in portfolioWeights.weights]
    update_portfolio_weights(portfolioWeights.portfolio_id, weights)


@router.post("/allocate-portfolio", response_model=AllocationResult)
async def allocate_portfolio_endpoint(request: AllocationRequest) -> AllocationResult:
    """
    Compute target weights for a portfolio using the selected allocation method.
    """
    try:
        return allocate_portfolio(request)
    except AllocationServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/rebalance-plan", response_model=RebalancePlan)
async def rebalance_plan_endpoint(request: RebalanceRequest) -> RebalancePlan:
    """
    Build a rebalance plan from current to target weights.
    If `apply=true`, target weights are written and synced via existing DB flow.
    """
    try:
        return build_rebalance_plan(request)
    except AllocationServiceError as exc:
        raise HTTPException(status_code=400, detail=f"allocation failed: {exc}")
    except RebalanceEngineError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/portfolios")
async def get_portfolios(rankBy: str | None = None, limit: int | None = None) -> PortfolioList:
    """
    Return a list of portfolios ranked by rankBy.
    """
    return get_ranked_list(rankBy, limit)


@router.get("/portfolios/summary")
async def get_portfolios_summary_endpoint() -> list[dict]:
    """
    Return all portfolios with return_percentage computed server-side in a single SQL query.
    """
    return get_portfolios_summary()


@router.get("/portfolio")
async def get_portfolio(portfolioName: str) -> Portfolio:
    """
    Return a portfolio with the given name.
    """
    return get_db_portfolio(portfolioName)


@router.post("/portfolio_id")
async def get_portfolio_by_id(portfolio_id: PortfolioID) -> Portfolio:
    """
    Return a portfolio with the given id.
    """
    return get_db_portfolio_id(portfolio_id.portfolio_id)


@router.get("/strategies")
async def get_strategies(rankBy: str | None = None, limit: int | None = None) -> StrategyList:
    """
    Return a list of strategies ranked by rankBy.
    """
    return get_ranked_strat_list(rankBy, limit)


@router.post("/strategy")
async def get_strategy(strategy: StrategyID) -> StrategyPrice:
    """
    Return a strategy by ID.
    """
    return get_db_strat(strategy.strategy_id)
