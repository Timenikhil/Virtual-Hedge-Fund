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
    total_value: number;
    return_percentage: number;
}

export interface Portfolios extends Array<Portfolio> {}

interface StrategyPrice { id: string; name: string; weight: number }
interface PerformancePoint { date: string; portfolio: number; [key: string]: number | string }

export interface PortfolioPrice {
    id: number;
    name: string;
    total_return: number;
    strategies: StrategyPrice[];
    performance: PerformancePoint[];
    topStrategyNames: string[];
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
        const response = await fetch(`${API_BASE_URL}/portfolios`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });
        if (!response.ok) throw new Error('Failed to fetch portfolios');
        const portfolios = (await response.json()).portfolios;

        return await Promise.all(
            portfolios.map(async (port: any) => {
                const strats: string[] = port.strategies ?? [];
                const weights: number[] = port.weights ?? [];

                if (strats.length === 0 || weights.length !== strats.length) {
                    return {
                        id: port.portfolio_id,
                        name: port.portfolio_name,
                        created_at: port.date ?? new Date().toISOString().split('T')[0],
                        strategy_count: strats.length,
                        total_value: 0,
                        return_percentage: 0,
                    };
                }

                // Fetch strategy details in parallel.
                const strategyDetails = await Promise.all(
                    strats.map((strategy_id: string) =>
                        fetch(`${API_BASE_URL}/strategy`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ strategy_id }),
                        }).then(res => res.ok ? res.json() : null)
                    )
                );

                const validDetails = strategyDetails.filter(Boolean);
                if (validDetails.length === 0) {
                    return {
                        id: port.portfolio_id,
                        name: port.portfolio_name,
                        created_at: port.date ?? new Date().toISOString().split('T')[0],
                        strategy_count: strats.length,
                        total_value: 0,
                        return_percentage: 0,
                    };
                }

                // Use the full price history to compute initial and current portfolio value.
                let initial_value = 0;
                let total_value = 0;
                validDetails.forEach((strat: any, index: number) => {
                    const prices: number[] = strat.prices ?? [];
                    const weight = weights[index] ?? 0;
                    if (prices.length > 0) {
                        initial_value += prices[0] * weight;
                        total_value += prices[prices.length - 1] * weight;
                    }
                });

                const return_percentage =
                    initial_value > 0
                        ? ((total_value - initial_value) / initial_value) * 100
                        : 0;

                return {
                    id: port.portfolio_id,
                    name: port.portfolio_name,
                    created_at: port.date ?? new Date().toISOString().split('T')[0],
                    strategy_count: strats.length,
                    total_value: Math.round(total_value),
                    return_percentage,
                };
            })
        );
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

        const performance: PerformancePoint[] = Array.from({ length: numPoints }, (_, i) => {
            const date = dates[i] ?? `Day ${i + 1}`;

            const portfolioValue = strategyDetails.reduce(
                (sum: number, strat: any, idx: number) =>
                    sum + (strat?.prices?.[i] ?? 0) * (weights[idx] ?? 0),
                0
            );

            const point: PerformancePoint = { date, portfolio: portfolioValue };
            top3.forEach((s, j) => {
                point[`strategy${j + 1}`] = top3Details[j]?.prices?.[i] ?? 0;
            });
            return point;
        });

        const firstPortfolio = performance[0]?.portfolio ?? 0;
        const lastPortfolio = performance[performance.length - 1]?.portfolio ?? 0;
        const total_return =
            firstPortfolio > 0
                ? ((lastPortfolio - firstPortfolio) / firstPortfolio) * 100
                : 0;

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
        initial_value: number = 100
    ): Promise<BacktestResult> => {
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? '';
        const body: any = { portfolio_id, method, rebalance_frequency_days, initial_value };
        if (start_date) body.start_date = start_date;
        if (end_date) body.end_date = end_date;

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
};
