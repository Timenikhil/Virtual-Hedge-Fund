const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface PortfolioRequest {
    portfolio_name: string;
    strategies: string[];
}

export const portfolioAPI = {
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