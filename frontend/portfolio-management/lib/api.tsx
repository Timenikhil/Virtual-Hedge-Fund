import { Strategy } from '@/components/StrategySelector';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface PortfolioRequest {
    portfolio_name: string;
    strategies: string[];
}

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
            weight: weights[index]
        }));


        //TODO : implement strat price extraction
        return {
            id: portfolio_id,
            name: port.portfolio_name,
            total_return: 12.5,
            strategies: formattedStrategies,
            performance: [
            { date: '2025-01-01', portfolio: 0, strategy1: 0, strategy2: 0, strategy3: 0 },
            { date: '2025-01-05', portfolio: 2.3, strategy1: 3.1, strategy2: 1.8, strategy3: 2.0 },
            { date: '2025-01-10', portfolio: 4.8, strategy1: 5.2, strategy2: 3.5, strategy3: 4.1 },
            { date: '2025-01-15', portfolio: 7.2, strategy1: 8.5, strategy2: 5.1, strategy3: 6.8 },
            { date: '2025-01-20', portfolio: 9.8, strategy1: 11.2, strategy2: 7.3, strategy3: 9.1 },
            { date: '2025-01-25', portfolio: 12.5, strategy1: 14.8, strategy2: 9.2, strategy3: 11.5 },
        ]
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

    aiSelectPool: async (poolName: string, prompt?: string): Promise<number> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-pool`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ poolName, prompt: prompt || null })
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