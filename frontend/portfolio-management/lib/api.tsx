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

interface StrategyPrice{ id: string, name: string, weight: number }
interface PerformancePrice { date: string, portfolio: number, strategy1: number, strategy2: number, strategy3: number }
export interface PortfolioPrice {
    id: number;
    name: string;
    total_return: number,
    strategies: StrategyPrice[],
    performance: PerformancePrice[]
}

export const portfolioAPI = {

    getStrategies: async(): Promise<Strategy[]> => {
        const response = await fetch(`${API_BASE_URL}/strategies`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) throw new Error('Failed to retrieve strategies');
        const strats = await response.json();
        return strats.strategies;
    },

    getPortfolios: async(): Promise<Portfolios> => {
            const response = await fetch(`${API_BASE_URL}/portfolios`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) throw new Error('Failed to fetch portfolios');
            const portfolios = (await response.json()).portfolios;

            // Map portfolios to add computed fields
            return await Promise.all(
                portfolios.map(async (port: any) => {
                    const strats = port.strategies;
                    const weights = port.weights;

                    // Fetch strategy details to get prices
                    const strategyDetails = await Promise.all(
                        strats.map((strategy_id: string) =>
                            fetch(`${API_BASE_URL}/strategy`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({strategy_id})
                            }).then(res => res.json())
                        )
                    );

                    // Calculate current portfolio value (last price point)
                    const lastIndex = strategyDetails[0]?.prices?.length - 1 || 0;
                    let total_value = strategyDetails.reduce((sum, strat, index) => {
                        const price = strat.prices[lastIndex];
                        const weight = weights[index];
                        return sum + (price * weight);
                    }, 0);

                    // Calculate initial portfolio value (first price point)
                    const initial_value = strategyDetails.reduce((sum, strat, index) => {
                        const price = strat.prices[0];
                        const weight = weights[index];
                        return sum + (price * weight);
                    }, 0);

                    // Calculate return percentage
                    const return_percentage = ((total_value - initial_value) / initial_value) * 100;
                    total_value *= 1000;
                    return {
                        id: port.portfolio_id,
                        name: port.portfolio_name,
                        created_at: port.date || new Date().toISOString().split('T')[0],
                        strategy_count: strats.length,
                        total_value,
                        return_percentage
                    };
                })
                );
        },

    getPortfolioDetails: async(pid : string): Promise<PortfolioPrice>=> {
        const portfolio_id = parseInt(pid)
        const response = await fetch(`${API_BASE_URL}/portfolio_id`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({portfolio_id})
        });
        if (!response.ok) throw new Error('Failed to fetch portfolio');
        const port = await response.json();
        const strats = port.strategies;
        const weights = port.weights;

        const strategyDetails = await Promise.all(
            strats.map((strategy_id: string) =>
                fetch(`${API_BASE_URL}/strategy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({strategy_id})})
                    .then(res => res.json())
            )
        );

        const formattedStrategies: StrategyPrice[] = strategyDetails.map((strat, index: number) => ({
            id: strat.strategy_id,
            name: strat.name,
            weight: weights[index] * 100
        }));

        const top3Strategies = [...formattedStrategies]
            .sort((a, b) => b.weight - a.weight)
            .slice(0, 3);

        const top3FullDetails = top3Strategies.map(s =>
            strategyDetails.find(sd => sd.strategy_id === s.id)
        );

        const numDataPoints = strategyDetails[0]?.prices?.length || 6;
        const startDate = new Date('2025-01-01');
        const intervalDays = 5;

        const dates = Array.from({ length: numDataPoints }, (_, i) => {
            const date = new Date(startDate);
            date.setDate(date.getDate() + (i * intervalDays));
            return date.toISOString().split('T')[0];
        });

        const performance: PerformancePrice[] = dates.map((date, dateIndex) => {
            // Top 3 strategy values for display
            const strategy1 = top3FullDetails[0]?.prices[dateIndex] || 0;
            const strategy2 = top3FullDetails[1]?.prices[dateIndex] || 0;
            const strategy3 = top3FullDetails[2]?.prices[dateIndex] || 0;

            // Portfolio value: dot product of ALL strategy prices and weights
            const portfolio = strategyDetails.reduce((sum, strat, index) => {
                const price = strat.prices[dateIndex]
                const weight = weights[index]
                return sum + (price * weight);
            }, 0);

            return {
                date,
                portfolio,
                strategy1,
                strategy2,
                strategy3
            };
        });

        const total_return = ((performance[performance.length - 1]?.portfolio - performance[0]?.portfolio)/performance[0]?.portfolio) * 100 || 0;
        return {
            id: portfolio_id,
            name: port.portfolio_name,
            total_return: total_return,
            strategies: formattedStrategies,
            performance: performance
        }

    },

    selectPool: async (data: PortfolioRequest): Promise<number> => {
        const response = await fetch(`${API_BASE_URL}/select-pool`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error('Failed to select pool');
        return await response.json();
    },

    aiSelectPool: async (poolName: string, account: string, prompt?: string): Promise<number> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-pool`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_name: poolName, account, prompt: prompt || null })
        });
        if (!response.ok) throw new Error('Failed to AI select pool');
        return await response.json();
    },

    selectPortfolio: async (portfolio_id: number, selector: string | null, k: number | null): Promise<string[]> => {
        const response = await fetch(`${API_BASE_URL}/select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                portfolio_id,
                selector: selector || null,
                k: k || null
            })
        });
        if (!response.ok) throw new Error('Failed to select portfolio');
        return await response.json();
    },

    aiSelectPortfolio: async (portfolio_id: number): Promise<string[]> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id })
        });
        if (!response.ok) throw new Error('Failed to AI select portfolio');
        return await response.json();
    },

    choosePortfolio: async (portfolio_id: number, strategies: string[]): Promise<void> => {
        const response = await fetch(`${API_BASE_URL}/choose-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id, strategies })
        });
        if (!response.ok) throw new Error('Failed to choose portfolio');
    },

    seedPortfolio: async (portfolio_id: number, weights: number[]): Promise<void> => {
        const total = weights.reduce((sum, w) => sum + w, 0);
        const normalizedWeights = weights.map(w => w / total);

        const response = await fetch(`${API_BASE_URL}/seed-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolio_id, weights: normalizedWeights })
        });
        if (!response.ok) throw new Error('Failed to seed portfolio');
    }

};
