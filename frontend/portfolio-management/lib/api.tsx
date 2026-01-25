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

    selectPortfolio: async (portfolioID: number, selector: string, k: number): Promise<void> => {
        const response = await fetch(`${API_BASE_URL}/select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolioID, selector, k })
        });
        if (!response.ok) throw new Error('Failed to select portfolio');
    },

    aiSelectPortfolio: async (portfolioID: number): Promise<void> => {
        const response = await fetch(`${API_BASE_URL}/ai-select-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolioID })
        });
        if (!response.ok) throw new Error('Failed to AI select portfolio');
    },

    choosePortfolio: async (portfolioID: number, strategies: string[]): Promise<void> => {
        const response = await fetch(`${API_BASE_URL}/choose-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolioID, strategies })
        });
        if (!response.ok) throw new Error('Failed to choose portfolio');
    },

    seedPortfolio: async (portfolioID: number, weights: number[]): Promise<void> => {
        const total = weights.reduce((sum, w) => sum + w, 0);
        const normalizedWeights = weights.map(w => w / total);

        const response = await fetch(`${API_BASE_URL}/seed-portfolio`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ portfolioID, weights: normalizedWeights })
        });
        if (!response.ok) throw new Error('Failed to seed portfolio');
    }
};