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

## Authentication

Admin routes (`/api/v1/admin/*`) require the `X-API-Key` header.

- Set `ADMIN_API_KEY` in your `.env` file.
- Missing or blank key → `503 Service Unavailable`.
- Wrong/missing header → `401 Unauthorized`.

The public API (`/api/v1/*`) has no authentication requirement.

## Backtesting

`POST /api/v1/admin/backtest` runs a historical simulation over stored strategy price data.

Request fields:
- `portfolio_id` — portfolio to backtest
- `method` — `equal_weight`, `score_weighted`, `ai_weighted`, or `manual`
- `rebalance_frequency_days` — how often to rebalance (default 30)
- `start_date` / `end_date` — optional ISO date filters
- `initial_value` — starting portfolio value (default 100)

Response includes:
- `total_return_pct`, `annualised_return_pct`, `sharpe_ratio`, `max_drawdown_pct`
- `daily_values` — `[date, value]` pairs for charting
- `strategy_legs` — per-strategy final weight and individual return

Notes:
- No look-ahead bias: weights at rebalance date `t` use only `prices[0..t]`.
- `ai_weighted` falls back to `score_weighted` to avoid calling Claude once per rebalance date.

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

### AI-Powered Pool Selection
`POST /api/v1/ai-select-pool` — accepts a natural language `prompt` and returns a portfolio ID.
Calls Claude (`claude-sonnet-4-6`) with the full list of available strategy IDs to select the best matching pool.
Falls back to all available strategies if `ANTHROPIC_API_KEY` is not set.

### AI in Reconcile Jobs
Recurring jobs can persist AI allocation parameters directly:
- `ai_provider_mode`
- `ai_strict`
- `ai_timeout_seconds`
- `ai_context`

These are forwarded into each scheduled rebalance/allocation run.

## Selector Behavior

Selector implementation:
- `topk`: first `k` strategies by current ordering
- `bottomk`: last `k` strategies
- `ai` selector mode: calls Claude to select the best `k` strategies from the available pool

`ai-select-pool` uses the Anthropic API to parse a natural language prompt against available strategy IDs.

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
- `vhf/api/auth.py` — API key authentication dependency
- `vhf/api/v1/public.py` — public routes (no auth)
- `vhf/api/v1/admin.py` — admin routes (auth required)
- `vhf/services/allocation_service.py`
- `vhf/services/backtest.py` — backtesting engine
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
- `DB_URL` — libSQL/Turso database URL
- `DB_TOKEN` — Turso auth token (leave blank for local SQLite)
- `ADMIN_API_KEY` — secret key for admin endpoints (`X-API-Key` header)
- `ANTHROPIC_API_KEY` — for AI allocation and AI pool/portfolio selection

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
- `RECONCILE_SCHEDULER_POLL_SECONDS` (default `60`) — how often the scheduler wakes up to check for due jobs. Must be ≤ the shortest `interval_seconds` of any reconcile job, otherwise jobs will run less frequently than configured.
- `RECONCILE_SCHEDULER_WORKER_ID` (optional)

## Testing

Run all tests:
```bash
poetry run python -m unittest discover -s tests -p 'test_*.py'
```

## Frontend (Next.js Dashboard)

Located in `frontend/portfolio-management/`.

Features:
- Portfolio list with return and strategy count
- Portfolio detail page: pie chart of weights, performance chart (portfolio vs top 3 strategies)
- Strategy weight editor (manual weight assignment with live rebalance)
- AI pool selection via natural language prompt
- Backtest page: configure method, rebalance frequency, date range, initial value; view return/Sharpe/drawdown metrics and daily value chart

Setup:
```bash
cd frontend/portfolio-management
pnpm install
pnpm dev
```

Dashboard available at `http://localhost:3000`.

## Current Boundaries

- Risk constraints are basic (no built-in sector caps, turnover limits, or volatility targeting).
- Scheduler is in-process; for production, consider Celery or a dedicated worker process.
- Realtime data collection requires a QuantRocket license.
