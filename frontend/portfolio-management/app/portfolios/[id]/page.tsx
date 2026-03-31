'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import {
    ArrowLeft, TrendingUp, TrendingDown, BarChart2, Pencil, Trash2, Check, X,
    PieChart as PieIcon, History, LineChart
} from 'lucide-react';
import {
    PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Legend,
    LineChart as ReLineChart, Line,
} from 'recharts';
import { portfolioAPI, AllocationSnapshot, RebalanceSnapshot } from '@/lib/api';
import StrategyWeightEditor from '@/components/StrategyWeightEditor';
import { useToast } from '@/contexts/ToastContext';

interface Strategy {
    id: string;
    name: string;
    weight: number;
}

interface PerformanceData {
    date: string;
    portfolio: number;
    equalWeight: number;
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
const STRATEGY_COLORS = ['#10b981', '#f59e0b', '#ef4444'];

type Tab = 'performance' | 'holdings' | 'history';

// ─────────────────────────────────────────────────────────────
// Performance Tab
// ─────────────────────────────────────────────────────────────
function PerformanceTab({ portfolio }: { portfolio: PortfolioDetails }) {
    const top3Names = portfolio.topStrategyNames ?? [];
    return (
        <div className="bg-white rounded-lg border p-6">
            <div className="flex items-center justify-between mb-1">
                <h2 className="text-xl font-semibold">Performance Over Time</h2>
                <span className="text-xs text-gray-400">All series indexed to 100</span>
            </div>
            <p className="text-sm text-gray-500 mb-4">
                Portfolio vs equal-weight benchmark vs top 3 strategies by weight
            </p>
            <ResponsiveContainer width="100%" height={420}>
                <AreaChart data={portfolio.performance}>
                    <defs>
                        <linearGradient id="gPortfolio" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="gEW" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.15} />
                            <stop offset="95%" stopColor="#94a3b8" stopOpacity={0} />
                        </linearGradient>
                        {STRATEGY_COLORS.map((c, i) => (
                            <linearGradient key={i} id={`gS${i}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={c} stopOpacity={0.2} />
                                <stop offset="95%" stopColor={c} stopOpacity={0} />
                            </linearGradient>
                        ))}
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                        dataKey="date"
                        tickFormatter={d => new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        tick={{ fontSize: 11 }}
                    />
                    <YAxis
                        domain={['auto', 'auto']}
                        tickFormatter={v => `${v.toFixed(0)}`}
                        label={{ value: 'Index (base 100)', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }}
                        tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                        formatter={(value: number | undefined) => value != null ? value.toFixed(1) : ''}
                        labelFormatter={d => new Date(d).toLocaleDateString()}
                        allowEscapeViewBox={{ x: false, y: true }}
                        wrapperStyle={{ zIndex: 10 }}
                    />
                    <Legend verticalAlign="top" wrapperStyle={{ paddingBottom: 12 }} />
                    <Area type="monotone" dataKey="portfolio" name="Portfolio" stroke="#3b82f6" strokeWidth={2.5}
                        fillOpacity={1} fill="url(#gPortfolio)" />
                    <Area type="monotone" dataKey="equalWeight" name="Equal-Weight" stroke="#94a3b8"
                        strokeWidth={1.5} strokeDasharray="5 3" fillOpacity={1} fill="url(#gEW)" />
                    {top3Names[0] && (
                        <Area type="monotone" dataKey="strategy1" name={top3Names[0]}
                            stroke={STRATEGY_COLORS[0]} strokeWidth={1.5} fillOpacity={1} fill="url(#gS0)" />
                    )}
                    {top3Names[1] && (
                        <Area type="monotone" dataKey="strategy2" name={top3Names[1]}
                            stroke={STRATEGY_COLORS[1]} strokeWidth={1.5} fillOpacity={1} fill="url(#gS1)" />
                    )}
                    {top3Names[2] && (
                        <Area type="monotone" dataKey="strategy3" name={top3Names[2]}
                            stroke={STRATEGY_COLORS[2]} strokeWidth={1.5} fillOpacity={1} fill="url(#gS2)" />
                    )}
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Holdings Tab
// ─────────────────────────────────────────────────────────────
function HoldingsTab({ portfolio }: { portfolio: PortfolioDetails }) {
    const router = useRouter();
    const pieData = portfolio.strategies.map(s => ({ name: s.name, value: s.weight }));
    return (
        <div className="grid grid-cols-2 gap-6">
            <div className="bg-white rounded-lg border p-6">
                <h2 className="text-xl font-semibold mb-4">Strategy Weight Distribution</h2>
                <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                        <Pie
                            data={pieData}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            label={({ name, value }) => `${name}: ${value}%`}
                            outerRadius={90}
                            dataKey="value"
                        >
                            {pieData.map((_, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip formatter={(v: number | undefined) => v != null ? `${v.toFixed(1)}%` : ''} />
                    </PieChart>
                </ResponsiveContainer>
                {/* Strategy list with links */}
                <div className="mt-3 space-y-1">
                    {portfolio.strategies.map((s, i) => (
                        <button
                            key={s.id}
                            onClick={() => router.push(`/strategies/${s.id}`)}
                            className="flex items-center gap-2 w-full text-left text-sm px-2 py-1 rounded hover:bg-gray-50 transition-colors"
                        >
                            <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                            <span className="flex-1 font-medium">{s.name}</span>
                            <span className="text-gray-400">{s.weight.toFixed(1)}%</span>
                        </button>
                    ))}
                </div>
            </div>
            <StrategyWeightEditor
                portfolioId={portfolio.id}
                strategies={portfolio.strategies}
                colors={COLORS}
                onWeightsUpdated={() => window.location.reload()}
            />
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// History Tab
// ─────────────────────────────────────────────────────────────
function WeightEvolutionChart({ history, strategies }: {
    history: AllocationSnapshot[];
    strategies: Strategy[];
}) {
    if (history.length === 0) return null;

    // Build data: one row per snapshot (oldest first)
    const sorted = [...history].reverse();
    const allStrats = strategies.map(s => s.id);
    const stratNames: Record<string, string> = {};
    strategies.forEach(s => { stratNames[s.id] = s.name; });

    const chartData = sorted.map(snap => {
        const row: any = { date: snap.created_at.split('T')[0] };
        snap.strategies.forEach((sid, i) => {
            row[sid] = Math.round((snap.target_weights[i] ?? 0) * 1000) / 10;
        });
        return row;
    });

    const lineColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

    return (
        <div className="bg-white rounded-lg border p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Weight Evolution</h2>
            <p className="text-sm text-gray-500 mb-4">How strategy allocations shifted over each rebalance</p>
            <ResponsiveContainer width="100%" height={280}>
                <ReLineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis
                        tickFormatter={v => `${v}%`}
                        domain={['auto', 'auto']}
                        tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                        formatter={(v: number | undefined) => v != null ? `${v.toFixed(1)}%` : ''}
                        allowEscapeViewBox={{ x: false, y: true }}
                        wrapperStyle={{ zIndex: 10 }}
                    />
                    <Legend verticalAlign="top" wrapperStyle={{ paddingBottom: 12 }} />
                    {allStrats.map((sid, i) => (
                        <Line
                            key={sid}
                            type="monotone"
                            dataKey={sid}
                            name={stratNames[sid] ?? sid}
                            stroke={lineColors[i % lineColors.length]}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                        />
                    ))}
                </ReLineChart>
            </ResponsiveContainer>
        </div>
    );
}

function AllocationTable({ history, strategies }: {
    history: AllocationSnapshot[];
    strategies: Strategy[];
}) {
    const stratNames: Record<string, string> = {};
    strategies.forEach(s => { stratNames[s.id] = s.name; });

    return (
        <div className="bg-white rounded-lg border p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Allocation History</h2>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b text-left text-gray-500">
                            <th className="pb-2 pr-4">Date</th>
                            <th className="pb-2 pr-4">Method</th>
                            <th className="pb-2">Target Weights</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history.map(snap => (
                            <tr key={snap.id} className="border-b last:border-0 hover:bg-gray-50">
                                <td className="py-2 pr-4 text-gray-600 whitespace-nowrap">
                                    {snap.created_at.split('T')[0]}
                                </td>
                                <td className="py-2 pr-4">
                                    <span className="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700 font-medium">
                                        {snap.method}
                                    </span>
                                </td>
                                <td className="py-2">
                                    <div className="flex flex-wrap gap-1">
                                        {snap.strategies.map((sid, i) => (
                                            <span key={sid} className="text-xs bg-gray-100 rounded px-2 py-0.5">
                                                {stratNames[sid] ?? sid}: {((snap.target_weights[i] ?? 0) * 100).toFixed(1)}%
                                            </span>
                                        ))}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function RebalanceTable({ history, strategies }: {
    history: RebalanceSnapshot[];
    strategies: Strategy[];
}) {
    const stratNames: Record<string, string> = {};
    strategies.forEach(s => { stratNames[s.id] = s.name; });

    return (
        <div className="bg-white rounded-lg border p-6">
            <h2 className="text-xl font-semibold mb-4">Rebalance History</h2>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b text-left text-gray-500">
                            <th className="pb-2 pr-4">Date</th>
                            <th className="pb-2 pr-4">Method</th>
                            <th className="pb-2 pr-4">Status</th>
                            <th className="pb-2">Trade Weights (Δ)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history.map(snap => (
                            <tr key={snap.id} className="border-b last:border-0 hover:bg-gray-50">
                                <td className="py-2 pr-4 text-gray-600 whitespace-nowrap">
                                    {snap.created_at.split('T')[0]}
                                </td>
                                <td className="py-2 pr-4">
                                    <span className="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700 font-medium">
                                        {snap.method}
                                    </span>
                                </td>
                                <td className="py-2 pr-4">
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                        snap.status === 'success'
                                            ? 'bg-green-50 text-green-700'
                                            : snap.status === 'failed'
                                            ? 'bg-red-50 text-red-700'
                                            : 'bg-gray-100 text-gray-600'
                                    }`}>
                                        {snap.status ?? 'unknown'}
                                    </span>
                                </td>
                                <td className="py-2">
                                    <div className="flex flex-wrap gap-1">
                                        {snap.strategies.map((sid, i) => {
                                            const delta = snap.trade_weights?.[i] ?? 0;
                                            return (
                                                <span key={sid} className={`text-xs rounded px-2 py-0.5 ${
                                                    delta > 0.001 ? 'bg-green-50 text-green-700'
                                                    : delta < -0.001 ? 'bg-red-50 text-red-700'
                                                    : 'bg-gray-100 text-gray-500'
                                                }`}>
                                                    {stratNames[sid] ?? sid}: {delta >= 0 ? '+' : ''}{(delta * 100).toFixed(1)}%
                                                </span>
                                            );
                                        })}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function HistoryTab({ portfolioId, strategies }: { portfolioId: number; strategies: Strategy[] }) {
    const [allocHistory, setAllocHistory] = useState<AllocationSnapshot[]>([]);
    const [rebalHistory, setRebalHistory] = useState<RebalanceSnapshot[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            portfolioAPI.getAllocationHistory(portfolioId),
            portfolioAPI.getRebalanceHistory(portfolioId),
        ]).then(([alloc, rebal]) => {
            setAllocHistory(alloc);
            setRebalHistory(rebal);
        }).catch(console.error).finally(() => setLoading(false));
    }, [portfolioId]);

    if (loading) return <div className="text-gray-500 py-8">Loading history...</div>;
    if (allocHistory.length === 0 && rebalHistory.length === 0) {
        return (
            <div className="bg-white rounded-lg border p-8 text-center text-gray-500">
                No allocation or rebalance history yet.
            </div>
        );
    }

    return (
        <>
            <WeightEvolutionChart history={allocHistory} strategies={strategies} />
            {allocHistory.length > 0 && (
                <AllocationTable history={allocHistory} strategies={strategies} />
            )}
            {rebalHistory.length > 0 && (
                <RebalanceTable history={rebalHistory} strategies={strategies} />
            )}
        </>
    );
}

// ─────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────
export default function PortfolioDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [portfolio, setPortfolio] = useState<PortfolioDetails | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<Tab>('performance');
    const [renaming, setRenaming] = useState(false);
    const [newName, setNewName] = useState('');
    const [deleting, setDeleting] = useState(false);

    const toast = useToast();

    const fetchPortfolioDetails = async () => {
        try {
            const data = await portfolioAPI.getPortfolioDetails(params.id as string);
            setPortfolio(data);
        } catch {
            toast.error('Failed to load portfolio');
        } finally {
            setLoading(false);
        }
    };

    const handleRename = async () => {
        if (!portfolio || !newName.trim()) return;
        try {
            await portfolioAPI.updatePortfolio(portfolio.id, newName.trim());
            setRenaming(false);
            fetchPortfolioDetails();
            toast.success('Portfolio renamed');
        } catch {
            toast.error('Failed to rename portfolio');
        }
    };

    const handleDelete = async () => {
        if (!portfolio) return;
        if (!confirm(`Delete portfolio "${portfolio.name}"? This cannot be undone.`)) return;
        setDeleting(true);
        try {
            await portfolioAPI.deletePortfolio(portfolio.id);
            router.push('/portfolios');
        } catch {
            toast.error('Failed to delete portfolio');
            setDeleting(false);
        }
    };

    useEffect(() => { fetchPortfolioDetails(); }, [params.id]);

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

    const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
        { id: 'performance', label: 'Performance', icon: <LineChart className="w-4 h-4" /> },
        { id: 'holdings',    label: 'Holdings',    icon: <PieIcon className="w-4 h-4" /> },
        { id: 'history',     label: 'History',     icon: <History className="w-4 h-4" /> },
    ];

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-7xl mx-auto px-6 py-8">
                    {/* Back */}
                    <button
                        onClick={() => router.push('/portfolios')}
                        className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
                    >
                        <ArrowLeft className="w-5 h-5" />
                        Back to Portfolios
                    </button>

                    {/* Header */}
                    <div className="mb-6 flex items-start justify-between">
                        <div>
                            {renaming ? (
                                <div className="flex items-center gap-2 mb-2">
                                    <input
                                        autoFocus
                                        value={newName}
                                        onChange={e => setNewName(e.target.value)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter') handleRename();
                                            if (e.key === 'Escape') setRenaming(false);
                                        }}
                                        className="text-2xl font-bold border-b-2 border-indigo-500 outline-none bg-transparent"
                                    />
                                    <button onClick={handleRename} className="text-green-600 hover:text-green-700">
                                        <Check className="w-5 h-5" />
                                    </button>
                                    <button onClick={() => setRenaming(false)} className="text-gray-400 hover:text-gray-600">
                                        <X className="w-5 h-5" />
                                    </button>
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 mb-2">
                                    <h1 className="text-3xl font-bold">{portfolio.name}</h1>
                                    <button
                                        onClick={() => { setNewName(portfolio.name); setRenaming(true); }}
                                        className="text-gray-400 hover:text-gray-600"
                                    >
                                        <Pencil className="w-4 h-4" />
                                    </button>
                                </div>
                            )}
                            <div className="flex items-center gap-2">
                                {portfolio.total_return >= 0
                                    ? <TrendingUp className="w-5 h-5 text-green-600" />
                                    : <TrendingDown className="w-5 h-5 text-red-600" />
                                }
                                <span className={`text-2xl font-semibold ${portfolio.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {portfolio.total_return >= 0 ? '+' : ''}{portfolio.total_return.toFixed(2)}%
                                </span>
                                <span className="text-gray-500 text-sm">Total Return</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <button
                                onClick={() => router.push(`/portfolios/${portfolio.id}/backtest`)}
                                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                            >
                                <BarChart2 className="w-4 h-4" />
                                Run Backtest
                            </button>
                            <button
                                onClick={handleDelete}
                                disabled={deleting}
                                className="flex items-center gap-2 px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-50 transition-colors"
                            >
                                <Trash2 className="w-4 h-4" />
                                Delete
                            </button>
                        </div>
                    </div>

                    {/* Tab bar */}
                    <div className="flex gap-1 mb-6 bg-white rounded-lg border p-1 w-fit">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    activeTab === tab.id
                                        ? 'bg-indigo-600 text-white'
                                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                                }`}
                            >
                                {tab.icon}
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Tab content */}
                    {activeTab === 'performance' && <PerformanceTab portfolio={portfolio} />}
                    {activeTab === 'holdings' && <HoldingsTab portfolio={portfolio} />}
                    {activeTab === 'history' && (
                        <HistoryTab portfolioId={portfolio.id} strategies={portfolio.strategies} />
                    )}
                </div>
            </div>
        </ProtectedRoute>
    );
}
