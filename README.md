# Virtual Hedge Fund (VHF)

VHF is a FastAPI backend for AI-driven portfolio management and backtesting, built as a Final Year Project (CP4101 B.Comp. Dissertation) at NUS School of Computing, AY2025/2026.

**Research question:** Can LLMs serve as practical portfolio weight allocators when given structured financial context, and what infrastructure properties are required to deploy them safely in a live trading environment?

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Poetry](https://python-poetry.org/docs/#installation) (`pip install poetry`)
- Python 3.13
- [pnpm](https://pnpm.io/installation) (for the frontend)

### 1. Clone and configure

```bash
git clone <repo-url>
cd Virtual-Hedge-Fund
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Description |
|---|---|
| `ADMIN_API_KEY` | Secret for admin endpoints (`X-API-Key` header) |
| `ANTHROPIC_API_KEY` | Required for AI-weighted allocation and AI pool selection |
| `NEXT_PUBLIC_ADMIN_API_KEY` | Same key — used by the frontend |

### 2. Install Python dependencies

```bash
poetry install
```

### 3. Start the API

```bash
# API only (no QuantRocket)
docker compose -f docker-compose.vhf.yml up --build

# API + full QuantRocket stack
poetry run poe up-all
```

API available at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`.

### 4. Start the frontend

```bash
cd frontend/portfolio-management
pnpm install
pnpm dev
```

Dashboard at `http://localhost:3000`.

### 5. Seed the database (optional)

Two seed scripts are available:

**Real market data (recommended)** — pulls historical ETF prices via yfinance (2005–present, ~21 years):

```bash
DB_PATH=volumes/appdata/vhf.db poetry run python scripts/seed_real.py
# Options:
#   --start-date 2005-01-01   (default)
#   --end-date   today        (default)
#   --dry-run                 preview without writing
```

Each strategy is proxied by a real ETF (MTUM, RSP, EFA, IVE, QUAL, USMV, XLK, TLT, LQD, SVXY). Fallback tickers are used for ETFs that launched after 2005.

**Synthetic data (GBM)** — generates deterministic price paths via Geometric Brownian Motion (no network required):

```bash
docker cp scripts/seed.py vhf-api:/app/seed.py
docker exec vhf-api python /app/seed.py
```

---

## Architecture

```
vhf/
├── api/v1/
│   ├── public.py          # Unauthenticated routes
│   └── admin.py           # Admin routes (X-API-Key required)
├── services/
│   ├── allocation_service.py   # Weight computation
│   ├── backtest.py             # Historical simulation engine
│   ├── rebalance_engine.py     # Drift-threshold rebalancing
│   ├── reconcile_service.py    # One-shot reconcile
│   └── reconcile_scheduler.py  # Distributed periodic scheduler
├── db/
│   ├── initialise.py      # Schema creation / migrations
│   └── operations.py      # All DB reads/writes
├── ai/
│   └── weight_allocator_provider.py  # Pluggable AI allocator
└── quantrocket/
    ├── backtest_sync.py   # QR Moonshot → price history ingestion
    └── cli.py             # Trade execution via QR CLI
```

---

## Core Features

### Portfolio Management

Create and manage portfolios of quantitative strategies.

```
POST /api/v1/select-pool          # Create portfolio from strategy list
GET  /api/v1/portfolios           # List portfolios
GET  /api/v1/strategies           # List strategies
POST /api/v1/allocate-portfolio   # Compute target weights
```

### Allocation Methods

| Method | Description |
|---|---|
| `equal_weight` | 1/N across all strategies |
| `score_weighted` | Proportional to end-to-end momentum |
| `manual` | Use stored portfolio weights |
| `ai_weighted` | Claude API allocates weights given structured context |

### Threshold-Based Rebalancing

Rebalance only when drift exceeds a configurable threshold (no-trade zone). Grounded in Davis & Norman (1990) and Vanguard (2024) threshold rebalancing research.

```
POST /api/v1/rebalance-plan
```

### Distributed Reconcile Scheduler

Recurring jobs with atomic DB claim/lock semantics to prevent duplicate execution across concurrent workers. Worker identity via `{hostname}:{pid}`.

```
POST /api/v1/admin/reconcile/jobs
POST /api/v1/admin/reconcile/scheduler/start
GET  /api/v1/admin/reconcile/scheduler/status
```

### Backtesting

Simulate a portfolio strategy over historical price data stored in the DB. No look-ahead bias — weights at each rebalance date use only prices visible at that point.

```
POST /api/v1/admin/backtest
GET  /api/v1/admin/backtest/{portfolio_id}/runs        # List saved runs
GET  /api/v1/admin/backtest/{portfolio_id}/runs/{id}   # Load a saved run
DELETE /api/v1/admin/backtest/{portfolio_id}/runs/{id} # Delete a saved run
```

Request fields:

| Field | Default | Description |
|---|---|---|
| `portfolio_id` | required | Portfolio to simulate |
| `method` | `equal_weight` | Allocation method |
| `rebalance_frequency_days` | `21` | ~Monthly rebalancing |
| `start_date` / `end_date` | auto | Optional ISO date clip |
| `initial_value` | `100` | Starting portfolio value |
| `live_ai_calls` | `false` | If true, call Claude at each rebalance (incurs API cost) |

Results include `rebalance_history` — the weight allocation at every rebalance date, keyed by strategy ID — used to render the weight evolution chart and rebalance log in the UI.

Every run is automatically persisted and appears in the "Past Runs" table on the backtest page.

### Loading Price History from QuantRocket

Before backtesting, each strategy needs historical price data. Trigger a QuantRocket Moonshot backtest and ingest the results:

```
POST /api/v1/admin/strategies/{strategy_id}/sync-backtest
GET  /api/v1/admin/strategies/{strategy_id}/sync-backtest/{job_id}  # Poll status
```

This calls the houston HTTP gateway (`http://houston/moonshot/backtests.csv`), converts daily returns to a cumulative price series (indexed to 100), and writes it to `strategy_price_history`.

Alternatively, POST price points directly:

```
POST /api/v1/admin/strategies/{strategy_id}/prices
Body: { "points": [["2025-01-02", 100.0], ["2025-01-03", 101.2], ...] }
```

### Batch Evaluation Script

Compare all portfolios across allocation methods and write a CSV + summary report:

```bash
# equal_weight and score_weighted (no API calls):
poetry run python scripts/evaluate.py

# Include live AI-weighted backtests:
poetry run python scripts/evaluate.py --live-ai

# Custom options:
poetry run python scripts/evaluate.py \
  --portfolio-ids 1,2 \
  --methods equal_weight,score_weighted,ai_weighted \
  --start-date 2025-01-02 \
  --end-date 2025-12-31 \
  --rebalance-days 21 \
  --output-dir results/
```

Output: `results/backtest_results.csv` and `results/backtest_summary.txt`.

> **Note:** Results in `volumes/appdata/results/` were generated using real ETF price history seeded via `scripts/seed_real.py` (yfinance, 2005–2026, ~21 years). Re-running against different price data will produce different numbers.

---

## AI Integration

### Pluggable Allocator Interface

The AI allocator is a protocol (`WeightAllocatorProvider`) with tiered fallback:

| Mode | Behaviour |
|---|---|
| `auto` | Try local (Claude API), then remote, then equal-weight |
| `local` | Call Anthropic Claude API directly |
| `remote` | POST context to `AI_ALLOCATOR_URL` |
| `disabled` | Skip AI, fall back to equal-weight |

Set via `AI_ALLOCATOR_MODE` in `.env`.

Accepted response shapes from the AI:
- `[w1, w2, ...]`
- `{"weights": [...]}`
- `{"allocations": {"SID1": 0.4, "SID2": 0.6}}`

### Structured Context Delivery

At each rebalance, the AI receives a formatted metrics table computed from the full price history visible at that point — not raw prices. Metrics per strategy:

| Metric | Description |
|---|---|
| `return_20d / 63d / 252d` | Recent momentum over 1M, 3M, 1Y windows |
| `return_cum_pct` | Full-history cumulative return |
| `vol_63d_ann_pct` | Annualised 63-day volatility |
| `sharpe_252d` | Annualised 1-year Sharpe ratio |
| `max_drawdown_pct` | Maximum drawdown over full history |

This structured context (rather than raw price arrays) is the primary mechanism enabling meaningful AI allocation decisions.

### Live AI Backtesting

Set `live_ai_calls=true` to call Claude at each rebalance date during a backtest, using only prices visible at that point (no look-ahead). The result includes:

- `ai_call_count` — number of successful Claude calls
- `ai_fallback_count` — fallbacks to equal-weight on error
- `weight_stability` — average per-strategy weight std dev across rebalances (lower = more consistent)

### AI Pool Selection

```
POST /api/v1/ai-select-pool
Body: { "portfolio_name": "...", "account": "...", "prompt": "I want equity momentum strategies" }
```

Uses `claude-sonnet-4-6` to select the best matching strategy pool from available strategies.

---

## Data Model

| Table | Purpose |
|---|---|
| `portfolios` | Portfolio records with strategy list and weights |
| `strategies` | Strategy metadata |
| `portfolio_accounts` | Portfolio → broker account mapping |
| `portfolio_allocations` | Allocation run audit trail |
| `rebalance_runs` | Rebalance plan snapshots |
| `reconcile_jobs` | Scheduled reconcile job definitions |
| `strategy_price_history` | Per-strategy `(date, price)` series |
| `backtest_results` | Persisted backtest runs (full result JSON) |

SQLite file location: `DB_PATH` env var (default: `/app/data/vhf.db` in container, `./volumes/appdata/vhf.db` via volume mount).

---

## Authentication

Admin routes (`/api/v1/admin/*`) require:

```
X-API-Key: <ADMIN_API_KEY>
```

- Missing key → `503 Service Unavailable`
- Wrong key → `401 Unauthorized`

---

## Testing

```bash
poetry run python -m unittest discover -s tests -p 'test_*.py'
```

137 tests across allocation, rebalance, reconcile, scheduler, selector, backtest, backtest sync, and persistence logic. All DB and network calls are mocked.

---

## Scheduler Notes

The reconcile scheduler runs in-process with the API.

| Env var | Default | Description |
|---|---|---|
| `RECONCILE_SCHEDULER_ENABLED` | `true` | Enable/disable on startup |
| `RECONCILE_SCHEDULER_POLL_SECONDS` | `60` | Wake-up interval; must be ≤ shortest job interval |
| `RECONCILE_SCHEDULER_WORKER_ID` | `{hostname}:{pid}` | Used for distributed lock claims |

---

## QuantRocket Setup (one-time, if using live data)

1. Obtain a QuantRocket license at `https://www.quantrocket.com/account/`
2. Start the full stack: `poetry run poe up-all`
3. In the QuantRocket Jupyter environment (`http://localhost:8888`):

```python
from quantrocket.license import set_license
from quantrocket.history import create_usstock_db, collect_history
from quantrocket.master import get_securities, create_universe

set_license("<YOUR_LICENSE_KEY>")
create_usstock_db("usstock-free-1d", bar_size="1 day", free=True)
collect_history("usstock-free-1d")
```

4. Run Moonshot backtests from the `intro_moonshot/` notebooks.
5. Sync strategy price history via `POST /api/v1/admin/strategies/{id}/sync-backtest`.
