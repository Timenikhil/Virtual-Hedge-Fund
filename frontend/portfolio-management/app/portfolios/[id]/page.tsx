'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ArrowLeft, TrendingUp, TrendingDown } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, AreaChart, Area, XAxis, YAxis, CartesianGrid, Legend } from 'recharts';

interface Strategy {
    id: string;
    name: string;
    weight: number;
}

interface PerformanceData {
    date: string;
    portfolio: number;
    strategy1?: number;
    strategy2?: number;
    strategy3?: number;
}

interface PortfolioDetails {
    id: number;
    name: string;
    total_return: number;
    strategies: Strategy[];
    performance: PerformanceData[];
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

export default function PortfolioDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [portfolio, setPortfolio] = useState<PortfolioDetails | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchPortfolioDetails = async () => {
        try {
            // TODO: Replace with actual API call
            // const data = await portfolioAPI.getPortfolioDetails(params.id as string);

            // Mock data
            setPortfolio({
                id: parseInt(params.id as string),
                name: 'Momentum Portfolio',
                total_return: 12.5,
                strategies: [
                    { id: 'strat-1', name: 'Momentum Strategy', weight: 35 },
                    { id: 'strat-2', name: 'Mean Reversion', weight: 25 },
                    { id: 'strat-3', name: 'Value Investing', weight: 20 },
                    { id: 'strat-4', name: 'Market Making', weight: 12 },
                    { id: 'strat-5', name: 'Pairs Trading', weight: 8 },
                ],
                performance: [
                    { date: '2025-01-01', portfolio: 0, strategy1: 0, strategy2: 0, strategy3: 0 },
                    { date: '2025-01-05', portfolio: 2.3, strategy1: 3.1, strategy2: 1.8, strategy3: 2.0 },
                    { date: '2025-01-10', portfolio: 4.8, strategy1: 5.2, strategy2: 3.5, strategy3: 4.1 },
                    { date: '2025-01-15', portfolio: 7.2, strategy1: 8.5, strategy2: 5.1, strategy3: 6.8 },
                    { date: '2025-01-20', portfolio: 9.8, strategy1: 11.2, strategy2: 7.3, strategy3: 9.1 },
                    { date: '2025-01-25', portfolio: 12.5, strategy1: 14.8, strategy2: 9.2, strategy3: 11.5 },
                ]
            });
            setLoading(false);
        } catch (error) {
            console.error('Error fetching portfolio details:', error);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPortfolioDetails();
    }, [params.id]);


    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-lg text-gray-600">Loading portfolio...</div>
                </div>
            </ProtectedRoute>
        );
    }

    if (!portfolio) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-lg text-gray-600">Portfolio not found</div>
                </div>
            </ProtectedRoute>
        );
    }

    const top3Strategies = [...portfolio.strategies]
        .sort((a, b) => b.weight - a.weight)
        .slice(0, 3);

    const pieData = portfolio.strategies.map(s => ({
        name: s.name,
        value: s.weight
    }));

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-7xl mx-auto px-6 py-8">
                    {/* Header */}
                    <button
                        onClick={() => router.push('/portfolios')}
                        className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
                    >
                        <ArrowLeft className="w-5 h-5" />
                        Back to Portfolios
                    </button>

                    <div className="mb-8">
                        <h1 className="text-3xl font-bold mb-2">{portfolio.name}</h1>
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-2">
                                {portfolio.total_return >= 0 ? (
                                    <TrendingUp className="w-5 h-5 text-green-600" />
                                ) : (
                                    <TrendingDown className="w-5 h-5 text-red-600" />
                                )}
                                <span className={`text-2xl font-semibold ${
                                    portfolio.total_return >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}>
                                    {portfolio.total_return >= 0 ? '+' : ''}{portfolio.total_return.toFixed(2)}%
                                </span>
                            </div>
                            <span className="text-gray-600">Total Return</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6 mb-8">
                        {/* Pie Chart - Weight Distribution */}
                        <div className="bg-white rounded-lg border p-6">
                            <h2 className="text-xl font-semibold mb-4">Strategy Weight Distribution</h2>
                            <ResponsiveContainer width="100%" height={300}>
                                <PieChart>
                                    <Pie
                                        data={pieData}
                                        cx="50%"
                                        cy="50%"
                                        labelLine={false}
                                        label={({ name, value }) => `${name}: ${value}%`}
                                        outerRadius={100}
                                        fill="#8884d8"
                                        dataKey="value"
                                    >
                                        {pieData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Strategy List */}
                        <div className="bg-white rounded-lg border p-6">
                            <h2 className="text-xl font-semibold mb-4">Strategies</h2>
                            <div className="space-y-3">
                                {portfolio.strategies.map((strategy, index) => (
                                    <div key={strategy.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-4 h-4 rounded"
                                                style={{ backgroundColor: COLORS[index % COLORS.length] }}
                                            />
                                            <span className="font-medium">{strategy.name}</span>
                                        </div>
                                        <span className="text-lg font-semibold">{strategy.weight}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Performance Chart */}
                    <div className="bg-white rounded-lg border p-6">
                        <h2 className="text-xl font-semibold mb-4">Performance Over Time</h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Portfolio vs Top 3 Strategies by Weight
                        </p>
                        <ResponsiveContainer width="100%" height={400}>
                            <AreaChart data={portfolio.performance}>
                                <defs>
                                    <linearGradient id="colorPortfolio" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                                    </linearGradient>
                                    <linearGradient id="colorStrategy1" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.6}/>
                                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                                    </linearGradient>
                                    <linearGradient id="colorStrategy2" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.6}/>
                                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                                    </linearGradient>
                                    <linearGradient id="colorStrategy3" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.6}/>
                                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis
                                    dataKey="date"
                                    tickFormatter={(date) => new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                />
                                <YAxis
                                    label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }}
                                />
                                <Tooltip
                                    formatter={(value: number) => `${value.toFixed(2)}%`}
                                    labelFormatter={(date) => new Date(date).toLocaleDateString()}
                                />
                                <Legend />
                                <Area
                                    type="monotone"
                                    dataKey="portfolio"
                                    name="Portfolio"
                                    stroke="#3b82f6"
                                    strokeWidth={3}
                                    fillOpacity={1}
                                    fill="url(#colorPortfolio)"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="strategy1"
                                    name={top3Strategies[0]?.name}
                                    stroke="#10b981"
                                    strokeWidth={2}
                                    fillOpacity={1}
                                    fill="url(#colorStrategy1)"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="strategy2"
                                    name={top3Strategies[1]?.name}
                                    stroke="#f59e0b"
                                    strokeWidth={2}
                                    fillOpacity={1}
                                    fill="url(#colorStrategy2)"
                                />
                                <Area
                                    type="monotone"
                                    dataKey="strategy3"
                                    name={top3Strategies[2]?.name}
                                    stroke="#ef4444"
                                    strokeWidth={2}
                                    fillOpacity={1}
                                    fill="url(#colorStrategy3)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </ProtectedRoute>
    );
}