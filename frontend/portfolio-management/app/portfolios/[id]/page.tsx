'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ArrowLeft, TrendingUp, TrendingDown, BarChart2 } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, AreaChart, Area, XAxis, YAxis, CartesianGrid, Legend } from 'recharts';
import {portfolioAPI} from "@/lib/api";
import StrategyWeightEditor from "@/components/StrategyWeightEditor";

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
    topStrategyNames: string[];
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

export default function PortfolioDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [portfolio, setPortfolio] = useState<PortfolioDetails | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchPortfolioDetails = async () => {
        try {
            const data = await portfolioAPI.getPortfolioDetails(params.id as string);
            setPortfolio(data);
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

    const top3Names = portfolio.topStrategyNames ?? [];

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

                    <div className="mb-8 flex items-start justify-between">
                        <div>
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
                        <button
                            onClick={() => router.push(`/portfolios/${portfolio.id}/backtest`)}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                        >
                            <BarChart2 className="w-4 h-4" />
                            Run Backtest
                        </button>
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

                        <StrategyWeightEditor
                            portfolioId={portfolio.id}
                            strategies={portfolio.strategies}
                            colors={COLORS}
                            onWeightsUpdated={() => {
                                window.location.reload();
                            }}
                        />
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
                                    label={{ value: 'Value (1K $)', angle: -90, position: 'insideLeft' }}
                                />
                                <Tooltip
                                    formatter={(value: number) => `${value.toFixed(0)} k$`}
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
                                {top3Names[0] && (
                                    <Area
                                        type="monotone"
                                        dataKey="strategy1"
                                        name={top3Names[0]}
                                        stroke="#10b981"
                                        strokeWidth={2}
                                        fillOpacity={1}
                                        fill="url(#colorStrategy1)"
                                    />
                                )}
                                {top3Names[1] && (
                                    <Area
                                        type="monotone"
                                        dataKey="strategy2"
                                        name={top3Names[1]}
                                        stroke="#f59e0b"
                                        strokeWidth={2}
                                        fillOpacity={1}
                                        fill="url(#colorStrategy2)"
                                    />
                                )}
                                {top3Names[2] && (
                                    <Area
                                        type="monotone"
                                        dataKey="strategy3"
                                        name={top3Names[2]}
                                        stroke="#ef4444"
                                        strokeWidth={2}
                                        fillOpacity={1}
                                        fill="url(#colorStrategy3)"
                                    />
                                )}
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </ProtectedRoute>
    );
}