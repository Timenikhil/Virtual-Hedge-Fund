# Virtual Hedge Fund (VHF) — Claude Context

## What this project is

This is a Final Year Project (FYP) for CP4101 B.Comp. Dissertation at the National University of Singapore (NUS), School of Computing, AY2025/2026. The project is titled **"AI in Financial Data Analytics and Trading: Virtual Hedge Fund"**.

The project is supervised under NUS SoC's FYP programme. The final report is due April 2026.

## Research motivation

Most AI trading research focuses on signal generation — producing alpha from individual strategies in isolation. This project addresses a different and underexplored problem: **given multiple quantitative strategies, how do you aggregate, allocate capital between them, rebalance safely, and execute trades in a live environment?**

In production hedge funds, this aggregation and allocation layer is still largely manual (Goldman Sachs Asset Management, 2024). This project builds the infrastructure to automate it, with AI-driven weight allocation at its core.

The key research question driving Jeffrey's contribution:
> Can LLMs serve as practical portfolio weight allocators when given structured financial context, and what infrastructure properties are required to deploy them safely in a live trading environment?

## Jeffrey's contribution areas

### 1. Pluggable AI allocator interface with tiered fallback
- `vhf/ai/weight_allocator_provider.py` — `WeightAllocatorProvider` protocol
- Supports `auto | local | remote | disabled` provider modes
- Strict mode re-raises on AI failure; non-strict mode falls back to equal-weight
- Timeout-bounded AI calls; flexible response parsing (list, dict, allocations map)
- Motivation: existing LLM finance research identifies real-world deployment safety as an open challenge (Chen et al., 2025; ACM ICAIF survey, 2024)

### 2. Threshold-filtered rebalance engine
- `vhf/services/rebalance_engine.py`
- Computes L1 drift and max absolute drift metrics
- Suppresses trades below configurable threshold (no-trade zone logic)
- Grounded in: Davis & Norman (1990), Donohue & Yip (2003), Vanguard threshold rebalancing research (2024)
- Motivation: calendar-based rebalancing wastes transaction costs; threshold-based rebalancing is theoretically and empirically superior

### 3. Distributed reconciliation scheduler with atomic job claiming
- `vhf/services/reconcile_scheduler.py`, `vhf/db/operations.py`
- Atomic DB lock via `claim_due_reconcile_jobs(worker_id)` — prevents double-execution across concurrent workers
- Stale lock timeout (3600s default) for fault recovery
- Worker identity via `{hostname}:{pid}`
- Motivation: duplicate trade execution in financial systems has real monetary cost; exactly-once semantics are a known distributed systems requirement

### 4. Supporting infrastructure
- Full audit trail: `portfolio_allocations`, `rebalance_runs`, `reconcile_jobs` tables
- Live-trading safety controls: execution toggle, dry-run mode
- Validated Pydantic models throughout; weight vector validation and normalisation
- API endpoints exposing all capabilities (`vhf/api/v1/`)
- Automated tests: 110+ unit tests across allocation, rebalance, reconcile, scheduler, selector, and backtest logic

## What is NOT Jeffrey's contribution
- QuantRocket strategy implementation (shared/external)
- The AI model itself — the `ai_weight_allocator` is a pluggable interface; Jeffrey built the infrastructure around it, not the model

## Academic framing

Jeffrey's work is framed as **applied AI systems research** — not a new trading strategy, but the deployment infrastructure that makes AI-driven portfolio management safe and operable. The three key contributions map to open problems identified in the literature:

| Contribution | Literature gap addressed |
|---|---|
| AI allocator interface + fallback | LLM deployment safety in finance (ACM ICAIF 2024) |
| Structured context delivery to LLM | LLMs struggle with precise allocation without structured data (FolioLLM, Stanford 2024) |
| Threshold rebalancing | No-trade zone theory applied to multi-strategy portfolios |
| Distributed scheduler | Exactly-once execution in financial job scheduling |

## Key papers to reference
- Goldman Sachs AM (2024) — multi-manager hedge fund allocation (motivation)
- Kisiel & Gorse (2021) — meta-portfolio management, adaptive allocator selection
- Davis & Norman (1990) — no-trade zone under transaction costs (foundational)
- Donohue & Yip (2003) — numerical verification of no-trade zone superiority
- Vanguard (2024) — threshold vs calendar rebalancing in practice
- ACM ICAIF LLM survey (2024) — deployment safety as open challenge
- ICLR 2025 workshop — LLM top-down sector allocation (identifies the gap this project fills)
- FolioLLM / Stanford (2024) — LLMs struggle with precise allocation without structured context
- DeMiguel et al. (2009) — 1/N diversification benchmark; explains why AI underperforms EW on cross-asset portfolios

## System architecture

```
QuantRocket (strategies) → Price history DB → Backtest / Allocation service
                                                    ↓
                                         AI context builder
                                         (_compute_strategy_metrics: 7 metrics from full history)
                                                    ↓
                                         Claude API (pluggable, timeout-bounded, fallback-safe)
                                                    ↓
                                         Weight vector → Normalise → Persist
                                                    ↓
                                         Rebalance engine (L1 drift threshold filter)
                                                    ↓
                                         Reconcile scheduler (atomic claim, exactly-once)
                                                    ↓
                                         QuantRocket execution
```

## Backtest evaluation results

**Data source:** Real ETF proxies via yfinance — 10 strategies mapped to ETFs (MTUM, RSP, EFA, IVE, QUAL, USMV, XLK, TLT, LQD, SVXY). Date range 2005–2026 (~21 years), covering GFC 2008, European debt crisis 2011, COVID 2020, 2022 rate hike cycle.

### AI context improvement story (evidence for contribution 2)

This is the core empirical evidence. The structured context pipeline is the variable being tested — not the AI model.

| Run | Data | AI context state | Alpha Fund AI vs EW | Key finding |
|---|---|---|---|---|
| Run 1 | GBM synthetic, 1yr | Broken: 20-price noise mislabelled as full history | -1.47pp | Synthetic data invalid; discarded |
| Run 2 | Real ETFs, 21yr | Still broken: raw 20-price slice sent to Claude | +50.68pp | Real data matters; context still wrong |
| Run 3 | Real ETFs, 21yr | Fixed: 7-metric structured table (returns, vol, Sharpe, drawdown) | +202.65pp | **Context quality is the dominant variable** |
| Run 4 | Real ETFs, 21yr | Same fixed context; 4 new portfolios tested | see table below | Pattern confirmed across 6 portfolios |

The +152pp improvement from Run 2 → Run 3 (same data, same model, only context changed) is the primary evidence that structured context delivery is a meaningful infrastructure concern, not just prompt tuning.

### Run 4 full results — 6 portfolios, ~863 live Claude API calls, 0 fallbacks

| Portfolio | Strategy mix | EW Return | AI Return | AI vs EW |
|---|---|---|---|---|
| Alpha Fund | 5 equity (momentum, value, sector) | 696% | 899% | **+203pp** |
| Momentum Trio | 3 equity momentum | 730% | 952% | **+222pp** |
| Factor Blend | 4 equity factors | 417% | 424% | +7pp |
| Diversified Fund | All 10 (cross-asset) | 512% | 397% | -115pp |
| Balanced Core | 4 cross-asset (equity + fixed income) | 391% | 245% | -147pp |
| Alternatives | 3 alternatives | 354% | 144% | -210pp |

**Pattern:** AI allocation adds clear value on homogeneous equity portfolios where strategies compete on the same return/risk dimensions. It underperforms equal-weight on cross-asset portfolios — consistent with DeMiguel et al. (2009): 1/N is hard to beat on diverse cross-asset portfolios even for sophisticated optimisers.

**What NOT to include in the report:** Mention cross-asset underperformance briefly in Limitations, cite DeMiguel, and move on.

## Report framing guidance

- This is **systems research**, not quant research. Emphasise correctness, safety, and operability — not alpha generation.
- The 3/6 AI win rate is academically defensible. Present it honestly alongside the DeMiguel (2009) benchmark context. Do not oversell it.
- The iterative context improvement (Run 1 → Run 3, +204pp on Alpha Fund) is the strongest evidence for contribution 2. Lead with it.
- The infrastructure (fallback, strict mode, atomic scheduler, threshold rebalancing) is the primary contribution — the evaluation validates it works at scale, not that the AI is a superior stock-picker.
- 863 live API calls with 0 fallbacks and 0 errors is itself a meaningful reliability result worth stating.
