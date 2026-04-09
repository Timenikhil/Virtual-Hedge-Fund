from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vhf.db.operations import (
    get_reconcile_job,
    update_reconcile_job_after_run,
)
from vhf.execution.alpaca_trade_api import (
    QuantRocketError,
    generate_orders_csv,
    trade_strategy_to_alpaca,
)
from vhf.logging.log import logger
from vhf.models.rebalance import RebalanceRequest
from vhf.models.reconcile import ReconcileRunResult, StrategyTradeResult
from vhf.services.allocation_service import AllocationServiceError
from vhf.services.rebalance_engine import RebalanceEngineError, build_rebalance_plan


class ReconcileServiceError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


_MAX_BACKOFF_SECONDS = 24 * 60 * 60  # cap at 24 h


def _next_run_iso(interval_seconds: int) -> str:
    return (_utc_now() + timedelta(seconds=interval_seconds)).isoformat()


def _backoff_next_run_iso(interval_seconds: int, consecutive_errors: int) -> str:
    """Exponential backoff: interval * 2^n, capped at _MAX_BACKOFF_SECONDS."""
    # Cap the exponent so 2**n never becomes astronomically large before min() clamps it.
    capped_n = min(consecutive_errors, 20)
    delay = min(interval_seconds * (2 ** capped_n), _MAX_BACKOFF_SECONDS)
    return (_utc_now() + timedelta(seconds=delay)).isoformat()


def run_reconcile_job(job_id: int) -> ReconcileRunResult:
    job = get_reconcile_job(job_id)
    if not job.enabled:
        raise ReconcileServiceError(f"Reconcile job {job_id} is disabled.")

    generated_at = _utc_now_iso()
    next_run_at = _next_run_iso(job.interval_seconds)

    try:
        plan = build_rebalance_plan(
            RebalanceRequest(
                portfolio_id=job.portfolio_id,
                method=job.method,
                threshold=job.threshold,
                apply=job.apply,
                ai_provider_mode=job.ai_provider_mode,
                ai_strict=job.ai_strict,
                ai_timeout_seconds=job.ai_timeout_seconds,
                ai_context=job.ai_context,
            )
        )

        plan_status = "applied" if plan.applied else ("needs_rebalance" if plan.rebalance_required else "noop")
        status = plan_status
        trade_results: list[StrategyTradeResult] = []
        trades_executed = False
        errors: list[str] = []

        if job.execute_trades:
            if not job.apply:
                raise ReconcileServiceError("execute_trades requires apply=true so weights and execution stay aligned.")

            if not plan.account:
                raise ReconcileServiceError(
                    f"Portfolio {job.portfolio_id} has no mapped account; cannot execute live trades safely."
                )

            trade_legs = [leg for leg in plan.legs if leg.trade_weight != 0]
            if trade_legs:
                trades_executed = True
                accounts = [plan.account]
                for leg in trade_legs:
                    strategy_id = leg.strategy_id
                    try:
                        if job.dry_run_trades:
                            csv_orders = generate_orders_csv(
                                strategy=strategy_id,
                                review_date=job.review_date,
                                accounts=accounts,
                            )
                            trade_results.append(
                                StrategyTradeResult(
                                    strategy_id=strategy_id,
                                    mode="dry_run",
                                    status="ok",
                                    detail={
                                        "rows": csv_orders.count("\n"),
                                        "action": leg.action,
                                        "trade_weight": leg.trade_weight,
                                    },
                                )
                            )
                        else:
                            trade_output = trade_strategy_to_alpaca(
                                strategy=strategy_id,
                                review_date=job.review_date,
                                accounts=accounts,
                            )
                            trade_results.append(
                                StrategyTradeResult(
                                    strategy_id=strategy_id,
                                    mode="live",
                                    status=str(trade_output.get("status", "ok")),
                                    detail={
                                        "action": leg.action,
                                        "trade_weight": leg.trade_weight,
                                        "trade_output": trade_output,
                                    },
                                )
                            )
                    except QuantRocketError as exc:
                        errors.append(f"{strategy_id}: {exc}")
                        trade_results.append(
                            StrategyTradeResult(
                                strategy_id=strategy_id,
                                mode="live" if not job.dry_run_trades else "dry_run",
                                status="error",
                                detail=str(exc),
                            )
                        )

        if errors:
            status = "partial_error"
        elif job.execute_trades and trades_executed and job.dry_run_trades:
            status = "dry_run"

        result = ReconcileRunResult(
            job_id=job.job_id,
            portfolio_id=job.portfolio_id,
            status=status,
            plan_status=plan_status,
            rebalance_required=plan.rebalance_required,
            applied=plan.applied,
            trades_executed=trades_executed,
            trade_results=trade_results,
            generated_at=generated_at,
        )

        update_reconcile_job_after_run(
            job_id=job.job_id,
            last_status=result.status,
            last_error="; ".join(errors) if errors else None,
            last_run_at=generated_at,
            next_run_at=next_run_at,
            success=not bool(errors),
        )
        return result

    except (AllocationServiceError, RebalanceEngineError, ReconcileServiceError) as exc:
        backoff_next_run = _backoff_next_run_iso(job.interval_seconds, job.consecutive_errors)
        update_reconcile_job_after_run(
            job_id=job.job_id,
            last_status="error",
            last_error=str(exc),
            last_run_at=generated_at,
            next_run_at=backoff_next_run,
            success=False,
        )
        raise
    except Exception as exc:
        backoff_next_run = _backoff_next_run_iso(job.interval_seconds, job.consecutive_errors)
        update_reconcile_job_after_run(
            job_id=job.job_id,
            last_status="error",
            last_error=f"unexpected: {exc}",
            last_run_at=generated_at,
            next_run_at=backoff_next_run,
            success=False,
        )
        logger.exception("Unexpected reconcile failure for job_id=%s", job.job_id)
        raise ReconcileServiceError(f"Unexpected reconcile failure: {exc}") from exc
