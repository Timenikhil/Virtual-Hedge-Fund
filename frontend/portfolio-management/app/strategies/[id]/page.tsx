'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ArrowLeft, TrendingUp, TrendingDown, Tag } from 'lucide-react';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

const API_BASE_URL = 'http://localhost:8000/api/v1';

interface StrategyDetail {
    strategy_id: string;
    name: string;
    description: string;
    category: string;
    prices: number[];
    dates: string[];
}

export default function StrategyDetailPage() {
    const { id } = useParams();
    const router = useRouter();
    const [strategy, setStrategy] = useState<StrategyDetail | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${API_BASE_URL}/strategy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy_id: id }),
        })
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(setStrategy)
            .catch(() => setStrategy(null))
            .finally(() => setLoading(false));
    }, [id]);

    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-gray-500">Loading strategy...</div>
                </div>
            </ProtectedRoute>
        );
    }

    if (!strategy) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                    <div className="text-gray-500">Strategy not found</div>
                </div>
            </ProtectedRoute>
        );
    }

    const prices = strategy.prices ?? [];
    const dates = strategy.dates ?? [];
    const firstPrice = prices[0] ?? 0;
    const lastPrice = prices[prices.length - 1] ?? 0;
    const totalReturn = firstPrice > 0 ? ((lastPrice - firstPrice) / firstPrice) * 100 : 0;
    const positive = totalReturn >= 0;

    const chartData = prices.map((p, i) => ({
        date: dates[i] ?? `Day ${i + 1}`,
        price: Math.round((p / firstPrice) * 100 * 100) / 100,
    }));

    const minPrice = Math.min(...chartData.map(d => d.price));
    const maxPrice = Math.max(...chartData.map(d => d.price));
    const padding = (maxPrice - minPrice) * 0.05;

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-4xl mx-auto px-6 py-8">
                    <button
                        onClick={() => router.back()}
                        className="flex items-center gap-2 text-gray-500 hover:text-gray-900 mb-6 text-sm"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back
                    </button>

                    {/* Header */}
                    <div className="bg-white rounded-lg border p-6 mb-6">
                        <div className="flex items-start justify-between">
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <h1 className="text-2xl font-bold">{strategy.name}</h1>
                                    <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700">
                                        <Tag className="w-3 h-3" />
                                        {strategy.category}
                                    </span>
                                </div>
                                <p className="text-gray-500">{strategy.description}</p>
                                <p className="text-xs text-gray-400 mt-1">ID: {strategy.strategy_id}</p>
                            </div>
                            <div className={`flex items-center gap-2 text-xl font-bold px-4 py-2 rounded-lg ${
                                positive ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                            }`}>
                                {positive ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                                {positive ? '+' : ''}{totalReturn.toFixed(2)}%
                            </div>
                        </div>

                        <div className="grid grid-cols-3 gap-4 mt-6 pt-4 border-t">
                            <div>
                                <p className="text-xs text-gray-400 mb-0.5">Start Price</p>
                                <p className="font-semibold">{firstPrice.toFixed(2)}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-400 mb-0.5">Current Price</p>
                                <p className="font-semibold">{lastPrice.toFixed(2)}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-400 mb-0.5">Data Points</p>
                                <p className="font-semibold">{prices.length} days</p>
                            </div>
                        </div>
                    </div>

                    {/* Chart */}
                    <div className="bg-white rounded-lg border p-6">
                        <div className="flex items-center justify-between mb-1">
                            <h2 className="text-lg font-semibold">Price History</h2>
                            <span className="text-xs text-gray-400">Indexed to 100</span>
                        </div>
                        <ResponsiveContainer width="100%" height={320}>
                            <AreaChart data={chartData}>
                                <defs>
                                    <linearGradient id="gStrategy" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={positive ? '#10b981' : '#ef4444'} stopOpacity={0.2} />
                                        <stop offset="95%" stopColor={positive ? '#10b981' : '#ef4444'} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                                <XAxis
                                    dataKey="date"
                                    tickFormatter={d => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                    tick={{ fontSize: 11 }}
                                />
                                <YAxis
                                    domain={[minPrice - padding, maxPrice + padding]}
                                    tickFormatter={v => v.toFixed(0)}
                                    tick={{ fontSize: 11 }}
                                />
                                <Tooltip
                                    formatter={(v: number | undefined) => v != null ? [`${v.toFixed(1)}`, 'Index'] : ''}
                                    labelFormatter={d => new Date(d).toLocaleDateString()}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="price"
                                    stroke={positive ? '#10b981' : '#ef4444'}
                                    strokeWidth={2}
                                    fillOpacity={1}
                                    fill="url(#gStrategy)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </ProtectedRoute>
    );
}
