'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { PortfolioStats } from '@/components/PortfolioStats';
import { PortfolioFilters } from '@/components/PortfolioFilters';
import { PortfolioTable } from '@/components/PortfolioTable';
import { EmptyPortfolioState } from '@/components/EmptyPortfolioState';
import { Plus } from 'lucide-react';

interface Portfolio {
    id: number;
    name: string;
    created_at: string;
    strategy_count: number;
    total_value?: number;
    return_percentage?: number;
}

export default function PortfoliosPage() {
    const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [filterStrategyCount, setFilterStrategyCount] = useState('');
    const [filterMinValue, setFilterMinValue] = useState('');
    const [filterMaxStrategyCount, setFilterMaxStrategyCount] = useState('');
    const [filterMaxValue, setFilterMaxValue] = useState('');
    const router = useRouter();

    useEffect(() => {
        fetchPortfolios();
    }, []);

    const fetchPortfolios = async () => {
        try {
            // Mock data
            setPortfolios([
                {
                    id: 1,
                    name: 'Momentum Portfolio',
                    created_at: '2025-01-20',
                    strategy_count: 5,
                    total_value: 125000,
                    return_percentage: 12.5
                },
                {
                    id: 2,
                    name: 'Value Strategy Mix',
                    created_at: '2025-01-15',
                    strategy_count: 3,
                    total_value: 85000,
                    return_percentage: -8.3
                }
            ]);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching portfolios:', error);
            setLoading(false);
        }
    };

    const filteredPortfolios = portfolios.filter(portfolio => {
        const matchesSearch = portfolio.name.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesMinStratCount = !filterStrategyCount || portfolio.strategy_count >= parseInt(filterStrategyCount);
        const matchesMaxStratCount = !filterMaxStrategyCount || portfolio.strategy_count <= parseInt(filterMaxStrategyCount);
        const matchesMinValue = !filterMinValue || (portfolio.total_value || 0) >= parseInt(filterMinValue);
        const matchesMaxValue = !filterMaxValue || (portfolio.total_value || 0) <= parseInt(filterMaxValue);
        return matchesSearch && matchesMinStratCount && matchesMaxStratCount && matchesMinValue && matchesMaxValue;
    });

    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-lg text-gray-600">Loading portfolios...</div>
                </div>
            </ProtectedRoute>
        );
    }

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-6xl mx-auto px-6 py-8">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-8">
                        <div>
                            <h1 className="text-3xl font-bold mb-2">My Portfolios</h1>
                            <p className="text-gray-600">Manage and monitor your meta-portfolios</p>
                        </div>
                        <button
                            onClick={() => router.push('/portfolios/create')}
                            className="flex items-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 shadow-sm"
                        >
                            <Plus className="w-5 h-5" />
                            Create Portfolio
                        </button>
                    </div>

                    <PortfolioStats portfolios={portfolios} />

                    <PortfolioFilters
                        searchQuery={searchQuery}
                        setSearchQuery={setSearchQuery}
                        filterStrategyCount={filterStrategyCount}
                        setFilterStrategyCount={setFilterStrategyCount}
                        filterMinValue={filterMinValue}
                        setFilterMinValue={setFilterMinValue}
                        filterMaxStrategyCount={filterMaxStrategyCount}
                        setFilterMaxStrategyCount={setFilterMaxStrategyCount}
                        filterMaxValue={filterMaxValue}
                        setFilterMaxValue={setFilterMaxValue}
                    />

                    {filteredPortfolios.length === 0 ? (
                        <EmptyPortfolioState hasPortfolios={portfolios.length > 0} />
                    ) : (
                        <PortfolioTable portfolios={filteredPortfolios} />
                    )}
                </div>
            </div>
        </ProtectedRoute>
    );
}