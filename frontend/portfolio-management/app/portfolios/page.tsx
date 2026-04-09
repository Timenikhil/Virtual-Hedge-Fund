'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { PortfolioStats } from '@/components/PortfolioStats';
import { PortfolioTable } from '@/components/PortfolioTable';
import { EmptyPortfolioState } from '@/components/EmptyPortfolioState';
import { Plus, Search } from 'lucide-react';
import { portfolioAPI, Portfolio } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';

export default function PortfoliosPage() {
    const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const router = useRouter();
    const toast = useToast();

    useEffect(() => {
        portfolioAPI.getPortfolios()
            .then(setPortfolios)
            .catch(() => toast.error('Failed to load portfolios'))
            .finally(() => setLoading(false));
    }, []);

    const filtered = portfolios.filter(p =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-gray-500">Loading portfolios...</div>
                </div>
            </ProtectedRoute>
        );
    }

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-5xl mx-auto px-6 py-8">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-8">
                        <div>
                            <h1 className="text-3xl font-bold mb-1">Portfolios</h1>
                            <p className="text-gray-500">Manage and monitor your meta-portfolios</p>
                        </div>
                        <button
                            onClick={() => router.push('/portfolios/create')}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
                        >
                            <Plus className="w-4 h-4" />
                            New Portfolio
                        </button>
                    </div>

                    <PortfolioStats portfolios={portfolios} />

                    {/* Search */}
                    {portfolios.length > 0 && (
                        <div className="relative mb-4">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search portfolios..."
                                value={searchQuery}
                                onChange={e => setSearchQuery(e.target.value)}
                                className="w-full pl-9 pr-4 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                            />
                        </div>
                    )}

                    {filtered.length === 0
                        ? <EmptyPortfolioState hasPortfolios={portfolios.length > 0} />
                        : <PortfolioTable portfolios={filtered} />
                    }
                </div>
            </div>
        </ProtectedRoute>
    );
}
