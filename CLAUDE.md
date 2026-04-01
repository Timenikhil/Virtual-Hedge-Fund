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

