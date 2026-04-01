'use client';

import React, { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ArrowLeft, Play, AlertTriangle } from 'lucide-react';
import {
    ComposedChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import { portfolioAPI, BacktestResult } from '@/lib/api';

const METHODS = [
    { value: 'equal_weight', label: 'Equal Weight' },
    { value: 'score_weighted', label: 'Score Weighted (Momentum)' },
    { value: 'ai_weighted', label: 'AI Weighted' },
    { value: 'manual', label: 'Manual (Current Weights)' },
];

function StatCard({
    label,
    value,
    positive,
    subtitle,
}: {
    label: string;
    value: string;
    positive?: boolean;
    subtitle?: string;
}) {
    const color =
        positive === undefined
            ? 'text-gray-900'
            : positive
            ? 'text-green-600'
            : 'text-red-600';
    return (
        <div className="bg-white rounded-lg border p-5">
            <p className="text-sm text-gray-500 mb-1">{label}</p>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
        </div>
    );
}

export default function BacktestPage() {
    const params = useParams();
    const router = useRouter();
    const portfolioId = parseInt(params.id as string, 10);

    const [method, setMethod] = useState('equal_weight');
    const [rebalanceDays, setRebalanceDays] = useState(30);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [initialValue, setInitialValue] = useState(100);
    const [liveAi, setLiveAi] = useState(false);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<BacktestResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    const runBacktest = async () => {
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const data = await portfolioAPI.runBacktest(
                portfolioId,
                method,
                rebalanceDays,
                startDate || undefined,
                endDate || undefined,
                initialValue,
                liveAi,
            );
            setResult(data);
        } catch (e: any) {
            setError(e.message ?? 'Backtest failed');
        } finally {
            setLoading(false);
        }
    };

    const chartData = result?.daily_values.map(([date, value]) => ({
        date,
        value: Math.round(value * 100) / 100,
    }));

    // Weight evolution: one data point per rebalance snapshot, one key per strategy
    const weightChartData = result?.rebalance_history.map(snap => {
        const point: Record<string, string | number> = { date: snap.date };
        for (const [sid, w] of Object.entries(snap.weights)) {
            point[sid] = Math.round(w * 10000) / 100; // → percent, 2dp
        }
        return point;
    });
    const strategyIds = result ? Object.keys(result.rebalance_history[0]?.weights ?? {}) : [];
    const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-7xl mx-auto px-6 py-8">
                    {/* Header */}
                    <button
                        onClick={() => router.push(`/portfolios/${portfolioId}`)}
                        className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
                    >
                        <ArrowLeft className="w-5 h-5" />
                        Back to Portfolio
                    </button>

                    <h1 className="text-3xl font-bold mb-8">Backtest</h1>

                    {/* Configuration */}
                    <div className="bg-white rounded-lg border p-6 mb-8">
                        <h2 className="text-xl font-semibold mb-4">Configuration</h2>
                        <div className="grid grid-cols-2 gap-6">
                            {/* Method */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Allocation Method
                                </label>
                                <select
                                    value={method}
                                    onChange={e => setMethod(e.target.value)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                >
                                    {METHODS.map(m => (
                                        <option key={m.value} value={m.value}>
                                            {m.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {/* Rebalance frequency */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Rebalance Frequency (trading days)
                                </label>
                                <input
                                    type="number"
                                    min={1}
                                    max={252}
                                    value={rebalanceDays}
                                    onChange={e => setRebalanceDays(parseInt(e.target.value) || 1)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>

                            {/* Start date */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Start Date <span className="text-gray-400">(optional)</span>
                                </label>
                                <input
                                    type="date"
                                    value={startDate}
                                    onChange={e => setStartDate(e.target.value)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>

                            {/* End date */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    End Date <span className="text-gray-400">(optional)</span>
                                </label>
                                <input
                                    type="date"
                                    value={endDate}
                                    onChange={e => setEndDate(e.target.value)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>

                            {/* Initial value */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Initial Portfolio Value ($)
                                </label>
                                <input
                                    type="number"
                                    min={1}
                                    value={initialValue}
                                    onChange={e => setInitialValue(parseFloat(e.target.value) || 100)}
                                    className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>
                        </div>

                        {/* Live AI calls toggle — only shown for ai_weighted */}
                        {method === 'ai_weighted' && (
                            <div className="mt-4 flex items-start gap-3 p-4 bg-indigo-50 border border-indigo-100 rounded-lg">
                                <input
                                    type="checkbox"
                                    id="liveAi"
                                    checked={liveAi}
                                    onChange={e => setLiveAi(e.target.checked)}
                                    className="mt-0.5 w-4 h-4 accent-indigo-600"
                                />
                                <div>
                                    <label htmlFor="liveAi" className="text-sm font-medium text-indigo-800 cursor-pointer">
                                        Live AI calls (Claude API)
                                    </label>
                                    <p className="text-xs text-indigo-600 mt-0.5">
                                        Calls Claude at each rebalance date using only prices visible at that point.
                                        Unchecked uses score-weighted as a fast proxy. Live calls incur API cost.
                                    </p>
                                </div>
                            </div>
                        )}

                        <button
                            onClick={runBacktest}
                            disabled={loading}
                            className="mt-6 flex items-center gap-2 px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            <Play className="w-4 h-4" />
                            {loading ? 'Running…' : 'Run Backtest'}
                        </button>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                            <p className="text-red-700">{error}</p>
                        </div>
                    )}

                    {/* Results */}
                    {result && (
                        <>
                            {/* Stat cards */}
                            <div className="grid grid-cols-4 gap-4 mb-8">
                                <StatCard
                                    label="Total Return"
                                    value={`${result.total_return_pct >= 0 ? '+' : ''}${result.total_return_pct.toFixed(2)}%`}
                                    positive={result.total_return_pct >= 0}
                                />
                                <StatCard
                                    label="Annualised Return"
                                    value={`${result.annualised_return_pct >= 0 ? '+' : ''}${result.annualised_return_pct.toFixed(2)}%`}
                                    positive={result.annualised_return_pct >= 0}
                                    subtitle="CAGR"
                                />
                                <StatCard
                                    label="Sharpe Ratio"
                                    value={result.sharpe_ratio != null ? result.sharpe_ratio.toFixed(3) : 'N/A'}
                                    positive={result.sharpe_ratio != null ? result.sharpe_ratio > 0 : undefined}
                                    subtitle="Risk-adjusted return"
                                />
                                <StatCard
                                    label="Max Drawdown"
                                    value={`${result.max_drawdown_pct.toFixed(2)}%`}
                                    positive={false}
                                    subtitle="Peak-to-trough decline"
                                />
                            </div>

                            <div className="grid grid-cols-3 gap-4 mb-8">
                                <StatCard
                                    label="Initial Value"
                                    value={`$${result.initial_value.toLocaleString()}`}
                                />
                                <StatCard
                                    label="Final Value"
                                    value={`$${result.final_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                                    positive={result.final_value >= result.initial_value}
                                />
                                <StatCard
                                    label="Trading Days / Rebalances"
                                    value={`${result.n_trading_days} / ${result.n_rebalances}`}
                                    subtitle={`${result.start_date} → ${result.end_date}`}
                                />
                            </div>

                            {/* AI allocation metrics — only shown when live AI was used */}
                            {result.ai_call_count != null && (
                                <div className="mb-8 p-4 bg-indigo-50 border border-indigo-100 rounded-lg">
                                    <h3 className="text-sm font-semibold text-indigo-800 mb-3">AI Allocator Metrics</h3>
                                    <div className="grid grid-cols-3 gap-4">
                                        <div>
                                            <p className="text-xs text-indigo-600">Claude calls</p>
                                            <p className="text-xl font-bold text-indigo-900">{result.ai_call_count}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-indigo-600">Fallbacks to equal-weight</p>
                                            <p className={`text-xl font-bold ${result.ai_fallback_count ? 'text-amber-600' : 'text-indigo-900'}`}>
                                                {result.ai_fallback_count ?? 0}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="text-xs text-indigo-600">Weight stability <span className="font-normal">(avg σ, lower = more consistent)</span></p>
                                            <p className="text-xl font-bold text-indigo-900">
                                                {result.weight_stability != null ? result.weight_stability.toFixed(4) : '—'}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Portfolio value chart */}
                            <div className="bg-white rounded-lg border p-6 mb-8">
                                <h2 className="text-xl font-semibold mb-4">Portfolio Value Over Time</h2>
                                <ResponsiveContainer width="100%" height={400}>
                                    <ComposedChart data={chartData}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis
                                            dataKey="date"
                                            tickFormatter={d =>
                                                new Date(d).toLocaleDateString('en-US', {
                                                    month: 'short',
                                                    day: 'numeric',
                                                })
                                            }
                                            minTickGap={40}
                                        />
                                        <YAxis
                                            tickFormatter={v => `$${v.toLocaleString()}`}
                                            width={80}
                                        />
                                        <Tooltip
                                            formatter={(v: number | undefined) =>
                                                v != null ? `$${v.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : ''
                                            }
                                            labelFormatter={d => new Date(d).toLocaleDateString()}
                                        />
                                        <Legend />
                                        <Line
                                            type="monotone"
                                            dataKey="value"
                                            name="Portfolio Value"
                                            stroke="#3b82f6"
                                            strokeWidth={2}
                                            dot={false}
                                        />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>

                            {/* Strategy legs */}
                            <div className="bg-white rounded-lg border p-6">
                                <h2 className="text-xl font-semibold mb-4">Strategy Legs (Final Weights)</h2>
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b text-left text-gray-500">
                                            <th className="pb-2 font-medium">Strategy ID</th>
                                            <th className="pb-2 font-medium text-right">Final Weight</th>
                                            <th className="pb-2 font-medium text-right">Total Return</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {result.strategy_legs.map(leg => (
                                            <tr key={leg.strategy_id} className="border-b last:border-0">
                                                <td className="py-2 font-mono text-gray-700">{leg.strategy_id}</td>
                                                <td className="py-2 text-right">
                                                    {(leg.final_weight * 100).toFixed(1)}%
                                                </td>
                                                <td
                                                    className={`py-2 text-right font-medium ${
                                                        leg.total_return_pct >= 0 ? 'text-green-600' : 'text-red-600'
                                                    }`}
                                                >
                                                    {leg.total_return_pct >= 0 ? '+' : ''}
                                                    {leg.total_return_pct.toFixed(2)}%
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            {/* Weight evolution chart — only meaningful with 2+ rebalances */}
                            {result.rebalance_history.length >= 2 && (
                                <div className="bg-white rounded-lg border p-6 mt-8">
                                    <h2 className="text-xl font-semibold mb-4">Weight Evolution at Each Rebalance</h2>
                                    <ResponsiveContainer width="100%" height={300}>
                                        <ComposedChart data={weightChartData}>
                                            <CartesianGrid strokeDasharray="3 3" />
                                            <XAxis
                                                dataKey="date"
                                                tickFormatter={d =>
                                                    new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                                                }
                                                minTickGap={40}
                                            />
                                            <YAxis
                                                tickFormatter={v => `${v}%`}
                                                domain={[0, 100]}
                                                width={50}
                                            />
                                            <Tooltip
                                                formatter={(v: number) => `${v.toFixed(2)}%`}
                                                labelFormatter={d => new Date(d).toLocaleDateString()}
                                            />
                                            <Legend />
                                            {strategyIds.map((sid, i) => (
                                                <Line
                                                    key={sid}
                                                    type="monotone"
                                                    dataKey={sid}
                                                    name={sid}
                                                    stroke={CHART_COLORS[i % CHART_COLORS.length]}
                                                    strokeWidth={2}
                                                    dot={{ r: 3 }}
                                                />
                                            ))}
                                        </ComposedChart>
                                    </ResponsiveContainer>
                                </div>
                            )}

                            {/* Rebalance log */}
                            {result.rebalance_history.length > 0 && (
                                <div className="bg-white rounded-lg border p-6 mt-8">
                                    <h2 className="text-xl font-semibold mb-4">
                                        Rebalance Log
                                        <span className="ml-2 text-sm font-normal text-gray-400">
                                            ({result.rebalance_history.length} snapshots incl. initial)
                                        </span>
                                    </h2>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b text-left text-gray-500">
                                                    <th className="pb-2 font-medium">Date</th>
                                                    <th className="pb-2 font-medium text-right">Portfolio Value</th>
                                                    {strategyIds.map(sid => (
                                                        <th key={sid} className="pb-2 font-medium text-right font-mono">
                                                            {sid}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {result.rebalance_history.map((snap, idx) => {
                                                    const prev = idx > 0 ? result.rebalance_history[idx - 1] : null;
                                                    return (
                                                        <tr key={snap.date} className="border-b last:border-0">
                                                            <td className="py-2 text-gray-700">
                                                                {new Date(snap.date).toLocaleDateString()}
                                                                {idx === 0 && (
                                                                    <span className="ml-2 text-xs text-indigo-500 font-medium">initial</span>
                                                                )}
                                                            </td>
                                                            <td className="py-2 text-right font-mono">
                                                                ${snap.portfolio_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                                            </td>
                                                            {strategyIds.map(sid => {
                                                                const w = snap.weights[sid] ?? 0;
                                                                const prevW = prev?.weights[sid] ?? w;
                                                                const delta = w - prevW;
                                                                return (
                                                                    <td key={sid} className="py-2 text-right">
                                                                        {(w * 100).toFixed(1)}%
                                                                        {prev && Math.abs(delta) >= 0.001 && (
                                                                            <span className={`ml-1 text-xs ${delta > 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                                                {delta > 0 ? '+' : ''}{(delta * 100).toFixed(1)}pp
                                                                            </span>
                                                                        )}
                                                                    </td>
                                                                );
                                                            })}
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </ProtectedRoute>
    );
}
