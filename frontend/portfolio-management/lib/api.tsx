import { Strategy } from '@/components/StrategySelector';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface PortfolioRequest {
    portfolio_name: string;
    account: string;
    strategies: string[];
}

export interface Portfolio {
    id: number;
    name: string;
    created_at: string;
    strategy_count: number;
    strategy_names: string[];
    total_value: number;
    return_percentage: number;
    live: boolean;
}

export interface Portfolios extends Array<Portfolio> {}

interface StrategyPrice { id: string; name: string; weight: number }
interface PerformancePoint { date: string; portfolio: number; equalWeight: number; [key: string]: number | string }

export interface PortfolioPrice {
    id: number;
    name: string;
    total_return: number;
    strategies: StrategyPrice[];
    performance: PerformancePoint[];
    topStrategyNames: string[];
}

export interface AdminStrategy {
    strategy_id: string;
    name: string;
    description: string;
    category: string;
    source: string;
}

export interface ReconcileJob {
    job_id: number;
    portfolio_id: number;
    interval_seconds: number;
    method: string;
    threshold: number;
    apply: boolean;
    execute_trades: boolean;
    dry_run_trades: boolean;
    enabled: boolean;
    next_run_at: string | null;
    last_run_at: string | null;
    last_status: string | null;
    last_error: string | null;
}

export interface AllocationSnapshot {
    id: number;
    portfolio_id: number;
    method: string;
    strategies: string[];
    raw_weights: number[];
    target_weights: number[];
    created_at: string;
}

export interface RebalanceSnapshot {
    id: number;
    portfolio_id: number;
    method: string;
    threshold: number;
    strategies: string[];
    current_weights: number[];
    target_weights: number[];
    trade_weights: number[];
    status: string | null;
    created_at: string;
}

export interface BacktestResult {
    portfolio_id: number;
    method: string;
    start_date: string;
    end_date: string;
    n_trading_days: number;
    n_rebalances: number;
    initial_value: number;
    final_value: number;
    total_return_pct: number;
    annualised_return_pct: number;
    sharpe_ratio: number | null;
    max_drawdown_pct: number;
    strategy_legs: { strategy_id: string; final_weight: number; total_return_pct: number }[];
    daily_values: [string, number][];
    // AI-specific metrics (only present when method=ai_weighted and live_ai_calls=true)
    ai_call_count: number | null;
    ai_fallback_count: number | null;
    weight_stability: number | null;
}

export const portfolioAPI = {

    getStrategies: async (): Promise<Strategy[]> => {
        const response = await fetch(`${API_BASE_URL}/strategies`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });
        if (!response.ok) throw new Error('Failed to retrieve strategies');
        const strats = await response.json();
        return strats.strategies;
    },

    getPortfolios: async (): Promise<Portfolios> => {
        const response = await fetch(`${API_BASE_URL}/portfolios/summary`);
        if (!response.ok) throw new Error('Failed to fetch portfolios');
        return response.json();
    },

    getPortfolioDetails: async (pid: string): Promise<PortfolioPrice> => {
        const portfolio_id = parseInt(pid, 10);
        const response = await fetch(`${API_BASE_URL}/portfolio_id`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id }),
        });
        if (!response.ok) throw new Error('Failed to fetch portfolio');
        const port = await response.json();
        const strats: string[] = port.strategies ?? [];
        const weights: number[] = port.weights ?? [];

        // Fetch all strategy details (with dates + prices) in parallel.
        const strategyDetails = await Promise.all(
            strats.map((strategy_id: string) =>
                fetch(`${API_BASE_URL}/strategy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ strategy_id }),
                }).then(res => res.ok ? res.json() : null)
            )
        );

        const formattedStrategies: StrategyPrice[] = strategyDetails.map(
            (strat: any, index: number) => ({
                id: strat?.strategy_id ?? strats[index],
                name: strat?.name ?? strats[index],
                weight: Math.round((weights[index] ?? 0) * 1000) / 10, // → 1 d.p. %
            })
        );

        // Pick top 3 by weight for individual chart lines.
        const top3 = [...formattedStrategies]
            .sort((a, b) => b.weight - a.weight)
            .slice(0, 3);
        const top3Details = top3.map(s =>
            strategyDetails.find((sd: any) => sd?.strategy_id === s.id)
        );

        // Use real dates from the first strategy that has them.
        const firstWithDates = strategyDetails.find((sd: any) => (sd?.dates?.length ?? 0) > 0);
        const dates: string[] = firstWithDates?.dates ?? [];
        const numPoints = Math.min(
            ...strategyDetails.map((sd: any) => sd?.prices?.length ?? 0),
            dates.length > 0 ? dates.length : Infinity
        );

        // Count strategies with price data for equal-weight benchmark
        const validStratCount = strategyDetails.filter((sd: any) => (sd?.prices?.length ?? 0) > 0).length;

        const rawPerformance = Array.from({ length: numPoints }, (_, i) => {
            const date = dates[i] ?? `Day ${i + 1}`;

            const portfolioValue = strategyDetails.reduce(
                (sum: number, strat: any, idx: number) =>
                    sum + (strat?.prices?.[i] ?? 0) * (weights[idx] ?? 0),
                0
            );

            const equalWeightValue = validStratCount > 0
                ? strategyDetails.reduce((sum: number, strat: any) => sum + (strat?.prices?.[i] ?? 0), 0) / validStratCount
                : 0;

            const point: any = { date, portfolio: portfolioValue, equalWeight: equalWeightValue };
            top3.forEach((_, j) => {
                point[`strategy${j + 1}`] = top3Details[j]?.prices?.[i] ?? 0;
            });
            return point;
        });

        // Normalize all series to index 100 from the first data point
        const norm = (val: number, base: number) => (base > 0 ? (val / base) * 100 : 100);
        const base = rawPerformance[0] ?? {};
        const basePortfolio = (base.portfolio as number) ?? 0;
        const baseEqualWeight = (base.equalWeight as number) ?? 0;
        const baseTop3 = top3.map((_, j) => (base[`strategy${j + 1}`] as number) ?? 0);

        const performance: PerformancePoint[] = rawPerformance.map(point => {
            const normalized: PerformancePoint = {
                date: point.date,
                portfolio: norm(point.portfolio, basePortfolio),
                equalWeight: norm(point.equalWeight, baseEqualWeight),
            };
            top3.forEach((_, j) => {
                normalized[`strategy${j + 1}`] = norm(point[`strategy${j + 1}`], baseTop3[j]);
            });
            return normalized;
        });

        const lastPortfolio = performance[performance.length - 1]?.portfolio ?? 100;
        const total_return = lastPortfolio - 100;

        return {
            id: portfolio_id,
            name: port.portfolio_name,
            total_return,
            strategies: formattedStrategies,
            performance,
            topStrategyNames: top3.map(s => s.name),
        };
    },

    runBacktest: async (
        portfolio_id: number,
        method: string,
        rebalance_frequency_days: number,
        start_date?: string,
        end_date?: string,
        initial_value: number = 100,
        live_ai_calls: boolean = false,
    ): Promise<BacktestResult> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const body: any = { portfolio_id, method, rebalance_frequency_days, initial_value };
        if (start_date) body.start_date = start_date;
        if (end_date) body.end_date = end_date;
        if (live_ai_calls) body.live_ai_calls = true;

        const response = await fetch(`${API_BASE_URL}/admin/backtest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey,
            },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error((err as any).detail ?? 'Backtest failed');
        }
        return response.json();
    },

    selectPool: async (data: PortfolioRequest): Promise<number> => {
        const response = await fetch(`${API_BASE_URL}/select-pool`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) throw new Error('Failed to select pool');
        return response.json();
    },

    aiSelectPool: async (poolName: string, account: string, prompt?: string): Promise<number> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-pool`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_name: poolName, account, prompt: prompt ?? null }),
        });
        if (!response.ok) throw new Error('Failed to AI select pool');
        return response.json();
    },

    selectPortfolio: async (
        portfolio_id: number,
        selector: string | null,
        k: number | null
    ): Promise<string[]> => {
        const response = await fetch(`${API_BASE_URL}/select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id, selector: selector ?? null, k: k ?? null }),
        });
        if (!response.ok) throw new Error('Failed to select portfolio');
        return response.json();
    },

    aiSelectPortfolio: async (portfolio_id: number): Promise<string[]> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id }),
        });
        if (!response.ok) throw new Error('Failed to AI select portfolio');
        return response.json();
    },

    choosePortfolio: async (portfolio_id: number, strategies: string[]): Promise<void> => {
        const response = await fetch(`${API_BASE_URL}/choose-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id, strategies }),
        });
        if (!response.ok) throw new Error('Failed to choose portfolio');
    },

    seedPortfolio: async (portfolio_id: number, weights: number[]): Promise<void> => {
        const total = weights.reduce((sum, w) => sum + w, 0);
        if (total <= 0) throw new Error('Weights must sum to a positive number');
        const normalizedWeights = weights.map(w => w / total);
        const response = await fetch(`${API_BASE_URL}/seed-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id, weights: normalizedWeights }),
        });
        if (!response.ok) throw new Error('Failed to seed portfolio');
    },

    // -------------------------------------------------------------------------
    // Admin: portfolio management
    // -------------------------------------------------------------------------

    adminListPortfolios: async (): Promise<{ id: number; name: string }[]> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/portfolios`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to list portfolios');
        const data = await response.json();
        return (data.portfolios ?? []).map((p: any) => ({ id: p.portfolio_id, name: p.portfolio_name }));
    },

    updatePortfolio: async (portfolio_id: number, portfolio_name?: string, account?: string): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const body: any = {};
        if (portfolio_name !== undefined) body.portfolio_name = portfolio_name;
        if (account !== undefined) body.account = account;
        const response = await fetch(`${API_BASE_URL}/admin/portfolios/${portfolio_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error('Failed to update portfolio');
    },

    deletePortfolio: async (portfolio_id: number): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/portfolios/${portfolio_id}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to delete portfolio');
    },

    getAllocationHistory: async (portfolio_id: number): Promise<AllocationSnapshot[]> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/portfolios/${portfolio_id}/allocation-history`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to fetch allocation history');
        return response.json();
    },

    getRebalanceHistory: async (portfolio_id: number): Promise<RebalanceSnapshot[]> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/portfolios/${portfolio_id}/rebalance-history`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to fetch rebalance history');
        return response.json();
    },

    // -------------------------------------------------------------------------
    // Admin: strategy management
    // -------------------------------------------------------------------------

    syncQRStrategies: async (): Promise<{ found: number; upserted: number; strategies: string[] }> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/strategies/sync-qr`, {
            method: 'POST',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to sync QR strategies');
        return response.json();
    },

    adminGetStrategies: async (): Promise<AdminStrategy[]> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/strategies`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to fetch strategies');
        return (await response.json()).strategies;
    },

    upsertStrategy: async (strategy_id: string, name: string, description: string, category: string): Promise<AdminStrategy> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/strategies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ strategy_id, name, description, category }),
        });
        if (!response.ok) throw new Error('Failed to upsert strategy');
        return response.json();
    },

    startStrategyBacktest: async (
        strategy_id: string,
        start_date?: string,
        end_date?: string,
    ): Promise<{ job_id: string; status: string }> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const body: any = {};
        if (start_date) body.start_date = start_date;
        if (end_date) body.end_date = end_date;
        const response = await fetch(`${API_BASE_URL}/admin/strategies/${strategy_id}/sync-backtest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error((err as any).detail ?? 'Failed to start backtest');
        }
        return response.json();
    },

    pollStrategyBacktest: async (
        strategy_id: string,
        job_id: string,
    ): Promise<{ status: string; points_stored?: number; detail?: string }> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/strategies/${strategy_id}/sync-backtest/${job_id}`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error((err as any).detail ?? 'Failed to poll backtest job');
        }
        return response.json();
    },

    deleteStrategy: async (strategy_id: string): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/strategies/${strategy_id}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to delete strategy');
    },

    // -------------------------------------------------------------------------
    // Admin: reconcile jobs
    // -------------------------------------------------------------------------

    listReconcileJobs: async (): Promise<ReconcileJob[]> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/jobs`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to list reconcile jobs');
        return response.json();
    },

    createReconcileJob: async (
        portfolio_id: number,
        interval_seconds: number,
        method: string,
        threshold: number,
        apply: boolean,
    ): Promise<ReconcileJob> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ portfolio_id, interval_seconds, method, threshold, apply }),
        });
        if (!response.ok) throw new Error('Failed to create reconcile job');
        return response.json();
    },

    runReconcileJob: async (job_id: number): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/jobs/${job_id}/run`, {
            method: 'POST',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error((err as any).detail ?? 'Failed to run reconcile job');
        }
    },

    setReconcileJobEnabled: async (job_id: number, enabled: boolean): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/jobs/${job_id}/enabled`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ enabled }),
        });
        if (!response.ok) throw new Error('Failed to update job');
    },

    deleteReconcileJob: async (job_id: number): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/jobs/${job_id}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to delete reconcile job');
    },

    // -------------------------------------------------------------------------
    // Admin: scheduler
    // -------------------------------------------------------------------------

    getSchedulerStatus: async (): Promise<{ enabled_by_config: boolean; running: boolean; poll_interval_seconds: number; next_poll_at: string | null }> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/scheduler/status`, {
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to get scheduler status');
        return response.json();
    },

    startScheduler: async (): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/scheduler/start`, {
            method: 'POST',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to start scheduler');
    },

    stopScheduler: async (): Promise<void> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const response = await fetch(`${API_BASE_URL}/admin/reconcile/scheduler/stop`, {
            method: 'POST',
            headers: { 'X-API-Key': apiKey },
        });
        if (!response.ok) throw new Error('Failed to stop scheduler');
    },
};
