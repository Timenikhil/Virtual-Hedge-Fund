'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { portfolioAPI, AdminStrategy, ReconcileJob } from '@/lib/api';
import { Play, Trash2, Plus, RefreshCw, Power, PowerOff, Clock, Cpu, Database, BarChart2 } from 'lucide-react';

const formatInterval = (seconds: number): string => {
    if (seconds >= 86400 && seconds % 86400 === 0) return `${seconds / 86400}d`;
    if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600}h`;
    if (seconds >= 60 && seconds % 60 === 0) return `${seconds / 60}m`;
    return `${seconds}s`;
};

// ---------------------------------------------------------------------------
// Scheduler panel
// ---------------------------------------------------------------------------

function SchedulerPanel() {
    const [status, setStatus] = useState<{ enabled_by_config: boolean; running: boolean; poll_interval_seconds: number; next_poll_at: string | null } | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [now, setNow] = useState(() => Date.now());

    const refreshing = React.useRef(false);

    useEffect(() => {
        const id = setInterval(() => {
            const n = Date.now();
            setNow(n);
            // Auto-refresh status a second after the countdown expires.
            if (
                status?.next_poll_at &&
                n >= new Date(status.next_poll_at).getTime() + 1000 &&
                !refreshing.current
            ) {
                refreshing.current = true;
                load().finally(() => { refreshing.current = false; });
            }
        }, 1000);
        return () => clearInterval(id);
    }, [status]);

    const load = async () => {
        try {
            setError(null);
            setStatus(await portfolioAPI.getSchedulerStatus());
        } catch (e: any) {
            setError(e.message ?? 'Failed to load scheduler status');
        }
    };

    useEffect(() => { load(); }, []);

    const toggle = async () => {
        setBusy(true);
        try {
            if (status?.running) await portfolioAPI.stopScheduler();
            else await portfolioAPI.startScheduler();
            await load();
        } finally { setBusy(false); }
    };

    const secondsUntil = status?.next_poll_at
        ? Math.max(0, Math.round((new Date(status.next_poll_at).getTime() - now) / 1000))
        : null;

    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Cpu className="w-5 h-5 text-indigo-500" />
                    <h2 className="text-base font-semibold text-gray-800">Reconcile Scheduler</h2>
                </div>
                <button onClick={load} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors">
                    <RefreshCw className="w-4 h-4" />
                </button>
            </div>

            <div className="px-6 py-5">
                {error ? (
                    <p className="text-sm text-red-500">{error}</p>
                ) : !status ? (
                    <p className="text-sm text-gray-400">Loading…</p>
                ) : (
                    <div className="flex items-center gap-6 flex-wrap">
                        {/* Status badge */}
                        <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
                            status.running ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-gray-100 text-gray-500 ring-1 ring-gray-200'
                        }`}>
                            <span className={`w-2 h-2 rounded-full ${status.running ? 'bg-emerald-500 animate-pulse' : 'bg-gray-400'}`} />
                            {status.running ? 'Running' : 'Stopped'}
                        </span>

                        {/* Poll interval */}
                        <div className="flex items-center gap-1.5 text-sm text-gray-500">
                            <Clock className="w-4 h-4 text-gray-400" />
                            <span>Poll every</span>
                            <span className="font-semibold text-gray-700">{formatInterval(status.poll_interval_seconds)}</span>
                            <span className="text-gray-400">({status.poll_interval_seconds}s)</span>
                        </div>

                        {/* Next poll countdown */}
                        {status.next_poll_at && secondsUntil !== null && (
                            <div className="flex items-center gap-1.5 text-sm text-gray-500">
                                <span>Next poll in</span>
                                <span className="font-semibold text-gray-700 tabular-nums w-8 text-right">{secondsUntil}s</span>
                                <span className="text-gray-400">({new Date(status.next_poll_at).toLocaleTimeString()})</span>
                            </div>
                        )}

                        {/* Toggle button */}
                        <button
                            onClick={toggle}
                            disabled={busy || !status.enabled_by_config}
                            className={`ml-auto flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                                status.running
                                    ? 'border border-red-200 text-red-600 hover:bg-red-50'
                                    : 'border border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                            }`}
                        >
                            {status.running ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
                            {status.running ? 'Stop' : 'Start'}
                        </button>

                        {!status.enabled_by_config && (
                            <p className="text-xs text-amber-600 w-full">Disabled by config — set RECONCILE_SCHEDULER_ENABLED=true to enable.</p>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Reconcile jobs panel
// ---------------------------------------------------------------------------

const METHODS = ['equal_weight', 'score_weighted', 'ai_weighted', 'manual'];

const METHOD_LABELS: Record<string, string> = {
    equal_weight: 'Equal Weight',
    score_weighted: 'Score Weighted',
    ai_weighted: 'AI Weighted',
    manual: 'Manual',
};

function ReconcileJobsPanel() {
    const [jobs, setJobs] = useState<ReconcileJob[]>([]);
    const [portfolios, setPortfolios] = useState<{ id: number; name: string }[]>([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [form, setForm] = useState({ portfolio_id: '', interval_seconds: '3600', method: 'equal_weight', threshold: '0.05', apply: false });
    const [busy, setBusy] = useState<Record<number, boolean>>({});
    const [error, setError] = useState<string | null>(null);

    const load = async () => {
        setLoading(true);
        try {
            const [j, p] = await Promise.all([
                portfolioAPI.listReconcileJobs(),
                portfolioAPI.adminListPortfolios(),
            ]);
            setJobs(j);
            setPortfolios(p);
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); }, []);

    const handleCreate = async () => {
        setError(null);
        try {
            await portfolioAPI.createReconcileJob(
                parseInt(form.portfolio_id),
                parseInt(form.interval_seconds),
                form.method,
                parseFloat(form.threshold),
                form.apply,
            );
            setCreating(false);
            setForm({ portfolio_id: '', interval_seconds: '3600', method: 'equal_weight', threshold: '0.05', apply: false });
            load();
        } catch (e: any) { setError(e.message); }
    };

    const handleRun = async (job_id: number) => {
        setBusy(b => ({ ...b, [job_id]: true }));
        setError(null);
        try { await portfolioAPI.runReconcileJob(job_id); await load(); }
        catch (e: any) { setError(e.message); }
        finally { setBusy(b => ({ ...b, [job_id]: false })); }
    };

    const handleToggle = async (job: ReconcileJob) => {
        setBusy(b => ({ ...b, [job.job_id]: true }));
        try { await portfolioAPI.setReconcileJobEnabled(job.job_id, !job.enabled); await load(); }
        finally { setBusy(b => ({ ...b, [job.job_id]: false })); }
    };

    const handleDelete = async (job_id: number) => {
        if (!confirm('Delete this reconcile job?')) return;
        setBusy(b => ({ ...b, [job_id]: true }));
        try { await portfolioAPI.deleteReconcileJob(job_id); await load(); }
        finally { setBusy(b => ({ ...b, [job_id]: false })); }
    };

    const inputCls = "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white";

    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Clock className="w-5 h-5 text-indigo-500" />
                    <h2 className="text-base font-semibold text-gray-800">Reconcile Jobs</h2>
                    {!loading && (
                        <span className="ml-1 px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-full">{jobs.length}</span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={load} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                    <button
                        onClick={() => setCreating(c => !c)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                    >
                        <Plus className="w-4 h-4" /> New Job
                    </button>
                </div>
            </div>

            <div className="px-6 py-5">
                {error && (
                    <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{error}</div>
                )}

                {creating && (
                    <div className="mb-5 border border-indigo-100 bg-indigo-50/40 rounded-xl p-5 grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1.5">Portfolio</label>
                            <select value={form.portfolio_id} onChange={e => setForm(f => ({ ...f, portfolio_id: e.target.value }))} className={inputCls}>
                                <option value="">Select…</option>
                                {portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1.5">Allocation Method</label>
                            <select value={form.method} onChange={e => setForm(f => ({ ...f, method: e.target.value }))} className={inputCls}>
                                {METHODS.map(m => <option key={m} value={m}>{METHOD_LABELS[m]}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1.5">Run every (seconds)</label>
                            <input type="number" value={form.interval_seconds}
                                onChange={e => setForm(f => ({ ...f, interval_seconds: e.target.value }))}
                                className={inputCls} />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1.5">Drift threshold (e.g. 0.05 = 5%)</label>
                            <input type="number" step="0.01" value={form.threshold}
                                onChange={e => setForm(f => ({ ...f, threshold: e.target.value }))}
                                className={inputCls} />
                        </div>
                        <div className="flex items-center gap-2">
                            <input type="checkbox" id="apply" checked={form.apply}
                                onChange={e => setForm(f => ({ ...f, apply: e.target.checked }))}
                                className="w-4 h-4 rounded accent-indigo-600" />
                            <label htmlFor="apply" className="text-sm text-gray-700">Apply weights after rebalance</label>
                        </div>
                        <div className="flex justify-end items-end gap-2">
                            <button onClick={() => setCreating(false)} className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors">Cancel</button>
                            <button onClick={handleCreate} disabled={!form.portfolio_id}
                                className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium">
                                Create
                            </button>
                        </div>
                    </div>
                )}

                {loading ? (
                    <p className="text-sm text-gray-400">Loading…</p>
                ) : jobs.length === 0 ? (
                    <div className="py-10 text-center">
                        <Clock className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                        <p className="text-sm text-gray-400">No reconcile jobs yet. Create one to get started.</p>
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wide border-b border-gray-100">
                                <th className="pb-2 pr-4">Portfolio</th>
                                <th className="pb-2 pr-4">Method</th>
                                <th className="pb-2 pr-4">Interval</th>
                                <th className="pb-2 pr-4">Last run</th>
                                <th className="pb-2 pr-4">Status</th>
                                <th className="pb-2 pr-4">Enabled</th>
                                <th className="pb-2"></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                            {jobs.map(job => (
                                <tr key={job.job_id} className="hover:bg-gray-50/50 transition-colors">
                                    <td className="py-3 pr-4 font-medium text-gray-800">
                                        {portfolios.find(p => p.id === job.portfolio_id)?.name ?? `#${job.portfolio_id}`}
                                    </td>
                                    <td className="py-3 pr-4">
                                        <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-md font-medium">
                                            {METHOD_LABELS[job.method] ?? job.method}
                                        </span>
                                    </td>
                                    <td className="py-3 pr-4 text-gray-600 tabular-nums">{formatInterval(job.interval_seconds)}</td>
                                    <td className="py-3 pr-4 text-xs text-gray-400">
                                        {job.last_run_at ? new Date(job.last_run_at).toLocaleString() : '—'}
                                    </td>
                                    <td className="py-3 pr-4">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                            job.last_status === 'success' ? 'bg-emerald-50 text-emerald-700' :
                                            job.last_status === 'error' ? 'bg-red-50 text-red-600' :
                                            'bg-gray-100 text-gray-500'
                                        }`}>
                                            {job.last_status ?? 'pending'}
                                        </span>
                                    </td>
                                    <td className="py-3 pr-4">
                                        <button title={job.enabled ? 'Disable' : 'Enable'} disabled={!!busy[job.job_id]}
                                            onClick={() => handleToggle(job)}
                                            className={`relative inline-flex h-5 w-9 rounded-full transition-colors disabled:opacity-40 ${
                                                job.enabled ? 'bg-emerald-500' : 'bg-gray-200'
                                            }`}>
                                            <span className={`inline-block w-4 h-4 bg-white rounded-full shadow-sm mt-0.5 transition-transform ${
                                                job.enabled ? 'translate-x-4' : 'translate-x-0.5'
                                            }`} />
                                        </button>
                                    </td>
                                    <td className="py-3">
                                        <div className="flex items-center gap-1">
                                            <button title="Run now" disabled={!!busy[job.job_id]} onClick={() => handleRun(job.job_id)}
                                                className="p-1.5 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-50 rounded-md transition-colors disabled:opacity-40">
                                                <Play className="w-3.5 h-3.5" />
                                            </button>
                                            <button title="Delete" disabled={!!busy[job.job_id]} onClick={() => handleDelete(job.job_id)}
                                                className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors disabled:opacity-40">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Strategy management panel
// ---------------------------------------------------------------------------

function StrategiesPanel() {
    const [strategies, setStrategies] = useState<AdminStrategy[]>([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [form, setForm] = useState({ strategy_id: '', name: '', description: '', category: '' });
    const [error, setError] = useState<string | null>(null);
    const [syncResult, setSyncResult] = useState<string | null>(null);

    // Per-row backtest sync state
    const [backtestExpanded, setBacktestExpanded] = useState<string | null>(null);
    const [backtestDates, setBacktestDates] = useState<Record<string, { start: string; end: string }>>({});
    const [backtestBusy, setBacktestBusy] = useState<Record<string, boolean>>({});
    const [backtestResult, setBacktestResult] = useState<Record<string, string>>({});

    const load = async () => {
        setLoading(true);
        try { setStrategies(await portfolioAPI.adminGetStrategies()); }
        finally { setLoading(false); }
    };

    const handleSyncQR = async () => {
        setSyncing(true);
        setSyncResult(null);
        setError(null);
        try {
            const result = await portfolioAPI.syncQRStrategies();
            setSyncResult(`Found ${result.found} QR strategies — ${result.upserted} upserted.`);
            load();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setSyncing(false);
        }
    };

    useEffect(() => { load(); }, []);

    const handleSyncBacktest = async (strategy_id: string) => {
        const dates = backtestDates[strategy_id] ?? { start: '', end: '' };
        setBacktestBusy(b => ({ ...b, [strategy_id]: true }));
        setBacktestResult(r => ({ ...r, [strategy_id]: 'Running...' }));
        setBacktestExpanded(null);
        setError(null);
        try {
            const { job_id } = await portfolioAPI.startStrategyBacktest(
                strategy_id,
                dates.start || undefined,
                dates.end || undefined,
            );
            // Poll until done or error
            const poll = async (): Promise<void> => {
                try {
                    const job = await portfolioAPI.pollStrategyBacktest(strategy_id, job_id);
                    if (job.status === 'running') {
                        setTimeout(poll, 3000);
                    } else if (job.status === 'done') {
                        setBacktestResult(r => ({ ...r, [strategy_id]: `✓ ${job.points_stored} points stored` }));
                        setBacktestBusy(b => ({ ...b, [strategy_id]: false }));
                    } else {
                        setBacktestResult(r => ({ ...r, [strategy_id]: `Error: ${job.detail}` }));
                        setBacktestBusy(b => ({ ...b, [strategy_id]: false }));
                    }
                } catch (e: any) {
                    setBacktestResult(r => ({ ...r, [strategy_id]: `Error: ${e.message}` }));
                    setBacktestBusy(b => ({ ...b, [strategy_id]: false }));
                }
            };
            setTimeout(poll, 3000);
        } catch (e: any) {
            setBacktestResult(r => ({ ...r, [strategy_id]: `Error: ${e.message}` }));
            setBacktestBusy(b => ({ ...b, [strategy_id]: false }));
        }
    };

    const handleCreate = async () => {
        setError(null);
        try {
            await portfolioAPI.upsertStrategy(form.strategy_id, form.name, form.description, form.category);
            setCreating(false);
            setForm({ strategy_id: '', name: '', description: '', category: '' });
            load();
        } catch (e: any) { setError(e.message); }
    };

    const handleDelete = async (strategy_id: string) => {
        if (!confirm(`Delete strategy "${strategy_id}"? This removes all its price history too.`)) return;
        try { await portfolioAPI.deleteStrategy(strategy_id); load(); }
        catch (e: any) { setError(e.message); }
    };

    const inputCls = "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white";

    return (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-indigo-500" />
                    <h2 className="text-base font-semibold text-gray-800">Strategies</h2>
                    {!loading && (
                        <span className="ml-1 px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-full">{strategies.length}</span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button onClick={load} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                    <button
                        onClick={handleSyncQR}
                        disabled={syncing}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 text-white text-sm font-medium rounded-lg hover:bg-amber-600 disabled:opacity-50 transition-colors"
                        title="Scan the QuantRocket codeload volume for Moonshot strategies"
                    >
                        <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
                        {syncing ? 'Scanning...' : 'Sync from QR'}
                    </button>
                    <button
                        onClick={() => setCreating(c => !c)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                    >
                        <Plus className="w-4 h-4" /> New Strategy
                    </button>
                </div>
            </div>

            <div className="px-6 py-5">
                {error && (
                    <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{error}</div>
                )}

                {creating && (
                    <div className="mb-5 border border-indigo-100 bg-indigo-50/40 rounded-xl p-5 grid grid-cols-2 gap-4">
                        {[
                            { key: 'strategy_id', label: 'Strategy ID', placeholder: 'e.g. momentum_us' },
                            { key: 'name', label: 'Display Name', placeholder: 'e.g. US Momentum' },
                            { key: 'description', label: 'Description', placeholder: 'Optional' },
                            { key: 'category', label: 'Category', placeholder: 'Optional' },
                        ].map(({ key, label, placeholder }) => (
                            <div key={key}>
                                <label className="block text-xs font-medium text-gray-600 mb-1.5">{label}</label>
                                <input value={(form as any)[key]} placeholder={placeholder}
                                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                                    className={inputCls} />
                            </div>
                        ))}
                        <div className="flex justify-end items-end gap-2 col-span-2">
                            <button onClick={() => setCreating(false)} className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors">Cancel</button>
                            <button onClick={handleCreate} disabled={!form.strategy_id || !form.name}
                                className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors font-medium">
                                Save
                            </button>
                        </div>
                    </div>
                )}

                {syncResult && (
                    <div className="mb-4 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">{syncResult}</div>
                )}

                {loading ? (
                    <p className="text-sm text-gray-400">Loading…</p>
                ) : strategies.length === 0 ? (
                    <div className="py-10 text-center">
                        <Database className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                        <p className="text-sm text-gray-400">No strategies found. Add one to get started.</p>
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wide border-b border-gray-100">
                                <th className="pb-2 pr-4">ID</th>
                                <th className="pb-2 pr-4">Name</th>
                                <th className="pb-2 pr-4">Source</th>
                                <th className="pb-2 pr-4">Category</th>
                                <th className="pb-2 pr-4">Description</th>
                                <th className="pb-2"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {strategies.map(s => (
                                <React.Fragment key={s.strategy_id}>
                                <tr className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                                    <td className="py-3 pr-4 font-mono text-xs text-gray-500 bg-gray-50/50">{s.strategy_id}</td>
                                    <td className="py-3 pr-4">
                                        <Link href={`/strategies/${s.strategy_id}`} className="font-medium text-gray-800 hover:text-indigo-600 transition-colors">
                                            {s.name}
                                        </Link>
                                    </td>
                                    <td className="py-3 pr-4">
                                        {s.source === 'quantrocket'
                                            ? <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-md font-medium">QR</span>
                                            : <span className="px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-md">Local</span>
                                        }
                                    </td>
                                    <td className="py-3 pr-4">
                                        {s.category
                                            ? <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-md">{s.category}</span>
                                            : <span className="text-gray-300">—</span>
                                        }
                                    </td>
                                    <td className="py-3 pr-4 text-gray-500 max-w-xs truncate">{s.description || <span className="text-gray-300">—</span>}</td>
                                    <td className="py-3">
                                        <div className="flex items-center gap-1">
                                            <button
                                                title="Sync backtest from QR"
                                                disabled={!!backtestBusy[s.strategy_id]}
                                                onClick={() => setBacktestExpanded(e => e === s.strategy_id ? null : s.strategy_id)}
                                                className={`p-1.5 rounded-md transition-colors disabled:opacity-40 ${
                                                    backtestExpanded === s.strategy_id
                                                        ? 'text-amber-600 bg-amber-50'
                                                        : 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'
                                                }`}
                                            >
                                                {backtestBusy[s.strategy_id]
                                                    ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                                    : <BarChart2 className="w-3.5 h-3.5" />
                                                }
                                            </button>
                                            <button onClick={() => handleDelete(s.strategy_id)}
                                                className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {(backtestBusy[s.strategy_id] || backtestResult[s.strategy_id]) && !backtestExpanded && (
                                    <tr className="border-b border-gray-50">
                                        <td colSpan={6} className="px-4 py-1.5 bg-gray-50/60">
                                            <div className="flex items-center gap-1.5 text-xs">
                                                {backtestBusy[s.strategy_id] && <RefreshCw className="w-3 h-3 animate-spin text-amber-500 shrink-0" />}
                                                <span className={
                                                    backtestResult[s.strategy_id]?.startsWith('✓') ? 'text-emerald-600' :
                                                    backtestResult[s.strategy_id]?.startsWith('Error') ? 'text-red-500' :
                                                    'text-amber-600'
                                                }>
                                                    {backtestResult[s.strategy_id] || 'Running…'}
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                                {backtestExpanded === s.strategy_id && (
                                    <tr className="bg-amber-50/50 border-b border-amber-100">
                                        <td colSpan={6} className="px-4 py-3">
                                            <div className="flex items-center gap-3 flex-wrap">
                                                <span className="text-xs font-medium text-amber-700">Sync backtest for <span className="font-mono">{s.strategy_id}</span></span>
                                                <div className="flex items-center gap-1.5">
                                                    <label className="text-xs text-gray-500">From</label>
                                                    <input
                                                        type="date"
                                                        value={backtestDates[s.strategy_id]?.start ?? ''}
                                                        onChange={e => setBacktestDates(d => ({ ...d, [s.strategy_id]: { ...d[s.strategy_id], start: e.target.value } }))}
                                                        className="border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400"
                                                    />
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <label className="text-xs text-gray-500">To</label>
                                                    <input
                                                        type="date"
                                                        value={backtestDates[s.strategy_id]?.end ?? ''}
                                                        onChange={e => setBacktestDates(d => ({ ...d, [s.strategy_id]: { ...d[s.strategy_id], end: e.target.value } }))}
                                                        className="border border-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400"
                                                    />
                                                </div>
                                                <span className="text-xs text-gray-400">Leave blank to use QR defaults</span>
                                                <button
                                                    onClick={() => handleSyncBacktest(s.strategy_id)}
                                                    disabled={!!backtestBusy[s.strategy_id]}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 text-white text-xs font-medium rounded-lg hover:bg-amber-600 disabled:opacity-50 transition-colors"
                                                >
                                                    <Play className="w-3 h-3" />
                                                    Run Backtest
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                                </React.Fragment>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gray-50">
                <div className="max-w-5xl mx-auto px-6 py-10">
                    <div className="mb-8">
                        <h1 className="text-2xl font-bold text-gray-900">Admin</h1>
                        <p className="text-sm text-gray-500 mt-1">Manage the scheduler, reconcile jobs, and strategies.</p>
                    </div>
                    <div className="space-y-5">
                        <SchedulerPanel />
                        <ReconcileJobsPanel />
                        <StrategiesPanel />
                    </div>
                </div>
            </div>
        </ProtectedRoute>
    );
}
