# Virtual Hedge Fund (VHF)

Virtual Hedge Fund is a FastAPI backend for building and running strategy portfolios.

At a high level, VHF is an orchestration service that:
- stores portfolios and strategy metadata
- computes target weights (manual, rules-based, or AI-driven)
- generates and applies rebalance plans
- schedules recurring reconcile jobs
- optionally executes trades through QuantRocket

## Core Capabilities

### Portfolio Management
- Create a portfolio with a strategy pool and mapped broker/account identifier.
- Update strategy membership for a portfolio.
- Seed/update portfolio weights.
- Query portfolios and strategies.

Primary routes:
- `POST /api/v1/select-pool`
- `POST /api/v1/select-portfolio`
- `POST /api/v1/choose-portfolio`
- `POST /api/v1/seed-portfolio`
- `GET /api/v1/portfolios`
- `GET /api/v1/strategies`

### Allocation Engine
Supported methods:
- `manual`
- `equal_weight`
- `score_weighted`
- `ai_weighted`

Behavior:
- validates and normalizes all weight vectors
- supports strict vs fallback behavior for AI allocation errors
- can persist normalized target weights back to the portfolio
- stores allocation snapshots for audit/debugging

Primary route:
- `POST /api/v1/allocate-portfolio`

### Rebalance Engine
- Builds rebalance legs (`buy` / `sell` / `hold`) from current vs target weights.
- Applies drift threshold filtering.
- Optionally applies target weights to portfolio state (`apply=true`).
- Stores rebalance run snapshots.

Primary route:
- `POST /api/v1/rebalance-plan`

### Reconcile Jobs + Scheduler
- Create recurring jobs with allocation method, threshold, interval, and execution behavior.
- Run manually or via in-process scheduler loop.
- Scheduler uses DB-backed claim/lock semantics to reduce duplicate execution across workers/instances.
- Job state tracks status/error/next-run timestamps.

Primary routes:
- `POST /api/v1/admin/reconcile/jobs`
- `GET /api/v1/admin/reconcile/jobs`
- `GET /api/v1/admin/reconcile/jobs/{job_id}`
- `POST /api/v1/admin/reconcile/jobs/{job_id}/run`
- `POST /api/v1/admin/reconcile/jobs/{job_id}/enabled`
- `POST /api/v1/admin/reconcile/scheduler/run-due`
- `POST /api/v1/admin/reconcile/scheduler/start`
- `POST /api/v1/admin/reconcile/scheduler/stop`
- `GET /api/v1/admin/reconcile/scheduler/status`

### Trading + Realtime Ops
- Dry-run orders CSV generation.
- Live one-shot trade invocation via QuantRocket CLI wrappers.
- Realtime DB create/list/start/stop helpers.

Primary routes:
- `POST /api/v1/admin/trade`
- `GET /api/v1/admin/orders.csv`
- `POST /api/v1/admin/realtime/create-tick-db`
- `POST /api/v1/admin/realtime/create-agg-db`
- `POST /api/v1/admin/realtime/start`
- `POST /api/v1/admin/realtime/stop`
- `GET /api/v1/admin/realtime/dbs`

## AI Integration

### AI Weight Allocator (for `ai_weighted`)
Provider modes:
- `auto`
- `local`
- `remote`
- `disabled`

Environment controls:
- `AI_ALLOCATOR_MODE`
- `AI_ALLOCATOR_LOCAL_MODULE` (default `vhf.ai.ai_weight_allocator`)
- `AI_ALLOCATOR_LOCAL_FUNCTION` (default `allocate_weights`)
- `AI_ALLOCATOR_URL`
- `AI_ALLOCATOR_API_KEY`

Accepted AI response payload shapes:
- `[w1, w2, ...]`
- `{"weights": [...]}`
- `{"target_weights": [...]}`
- `{"allocations": {"SID1": 0.2, "SID2": 0.8}}`
- `{"SID1": 0.2, "SID2": 0.8}`

### AI in Reconcile Jobs
Recurring jobs can persist AI allocation parameters directly:
- `ai_provider_mode`
- `ai_strict`
- `ai_timeout_seconds`
- `ai_context`

These are forwarded into each scheduled rebalance/allocation run.

## Selector Behavior

Current selector implementation is deterministic:
- `topk`: first `k` strategies
- `bottomk`: last `k` strategies
- `ai` selector mode currently falls back to `topk`

`ai-select-pool` prompt parsing currently extracts token-like strategy IDs from text.

## Ranking and Query Behavior

`GET /api/v1/portfolios` and `GET /api/v1/strategies` support `rankBy` and `limit`.

`rankBy` supports ascending or descending via `-` prefix.
Examples:
- `rankBy=name`
- `rankBy=-date`
- `rankBy=-p5`

Invalid `rankBy` values return `400`.

## Allocation Sync Safety

When syncing portfolio allocations to QuantRocket account mappings:
- portfolio must have weights
- number of weights must match number of strategies

Mismatch/missing states now fail fast (HTTP `409`) instead of silently truncating.

## Data Model (DB)

Core tables:
- `portfolios`
- `strategies`
- `portfolio_accounts`
- `portfolio_allocations`
- `rebalance_runs`
- `reconcile_jobs`
- `strategy_price_history`

Notes:
- strategy history supports more than legacy `P0..P5`; reads prefer `strategy_price_history` and fall back to legacy columns if history table has no rows for a strategy.
- reconcile jobs include lock fields (`LOCKED_AT`, `LOCKED_BY`) for scheduler claims.

## Runtime Architecture

1. FastAPI route receives request.
2. Service layer computes allocation/rebalance/reconcile logic.
3. DB operations persist state and audit artifacts.
4. QuantRocket adapters perform external sync/execution.

Main modules:
- `vhf/api/v1/public.py`
- `vhf/api/v1/admin.py`
- `vhf/services/allocation_service.py`
- `vhf/services/rebalance_engine.py`
- `vhf/services/reconcile_service.py`
- `vhf/services/reconcile_scheduler.py`
- `vhf/db/operations.py`
- `vhf/quantrocket/cli.py`

## Local Setup

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Poetry](https://python-poetry.org/docs/#installation)
- Python `3.13`

### Clone + Env
```bash
git clone <repo-url>
cd Virtual-Hedge-Fund
cp .env.example .env
```

Set required `.env` values, especially:
- `DB_URL`
- `DB_TOKEN`

### Install
```bash
poetry install
```

### Run
QuantRocket + API:
```bash
poetry run poe up-all
```

API only:
```bash
poetry run poe up-api
```

API docs:
- `http://localhost:8000/docs`

### QuantRocket Bootstrap (one-time)
References:
- https://www.quantrocket.com/account/
- https://www.quantrocket.com/docs/#deploy-license-key

Example:
```python
from quantrocket.license import set_license
from quantrocket.history import create_usstock_db, collect_history
from quantrocket.master import get_securities, create_universe
from quantrocket.history import list_sids

set_license("<YOUR_LICENSE_KEY>")
create_usstock_db("usstock-free-1d", bar_size="1 day", free=True)
collect_history("usstock-free-1d")

free_sids = list_sids("usstock-free-1d")
securities = get_securities(sids=free_sids)
create_universe("usstock-free", sids=securities.index.tolist())
```

## Scheduler Runtime Notes

The scheduler is in-process with the API process.
- If API is down, scheduler is down.
- Default poll interval is 1 day.
- Due-job execution uses claim/lock semantics in DB to reduce duplicate execution risk.

Env knobs:
- `RECONCILE_SCHEDULER_ENABLED` (default `true`)
- `RECONCILE_SCHEDULER_POLL_SECONDS` (default `86400`)
- `RECONCILE_SCHEDULER_WORKER_ID` (optional)

## Testing

Run all tests:
```bash
poetry run python -m unittest discover -s tests -p 'test_*.py'
```

## Current Boundaries

- No full historical portfolio simulation engine yet (multi-period backtest of dynamic weights).
- Risk constraints are basic (no built-in sector caps / turnover limits / volatility targeting).
- Admin/auth hardening is still needed for production deployment.
