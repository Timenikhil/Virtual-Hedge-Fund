'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Filter, Settings, Shuffle, Sliders, RefreshCw, ChevronDown, Play, ArrowLeft } from 'lucide-react';
import { portfolioAPI } from '@/lib/api';
import { StrategySelector, Strategy } from '@/components/StrategySelector';
import { StepCard } from '@/components/StepCard';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { useRouter } from 'next/navigation';
import { useToast } from '@/contexts/ToastContext';


export default function PortfolioManagement() {
    const router = useRouter();
    const toast = useToast();
    const [workflowMode, setWorkflowMode] = useState<'manual' | 'automatic'>('manual');
    const [currentStep, setCurrentStep] = useState(1);
    const [portfolioName, setPortfolioName] = useState('');
    const [accountName, setAccountName] = useState('');
    const [portfolioId, setPortfolioId] = useState<number | null>(null);
    const [strategies, setStrategies] = useState<Strategy[]>([]);
    const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
    const [aiPrompt, setAiPrompt] = useState('');
    const [selector, setSelector] = useState<string | null>('topk');
    const [selectorK, setSelectorK] = useState<number | null>(10);
    const [weights, setWeights] = useState<number[]>([]);

    const [loadingStep, setLoadingStep] = useState<number | null>(null);

    useEffect(() => {
        portfolioAPI.getStrategies().then(setStrategies).catch(() => {});
    }, []);

    const [stepStatus, setStepStatus] = useState({
        1: 'active' as 'active' | 'completed' | 'pending',
        2: 'pending' as 'active' | 'completed' | 'pending',
        3: 'pending' as 'active' | 'completed' | 'pending',
        4: 'pending' as 'active' | 'completed' | 'pending',
        5: 'pending' as 'active' | 'completed' | 'pending',
    });

    const handleStepComplete = useCallback((step: number) => {
        setStepStatus(prev => {
            const newStatus = { ...prev };
            newStatus[step as keyof typeof newStatus] = 'completed';
            if (step < 5) {
                newStatus[(step + 1) as keyof typeof newStatus] = 'active';
            }
            return newStatus;
        });
        if (step < 5) {
            setCurrentStep(step + 1);
        }
    }, []);

    const handleStep1Submit = async () => {
        setLoadingStep(1);
        try {
            let id: number;
            if (portfolioId !== null) {
                // Re-submitting: update strategies on the existing portfolio instead of creating a duplicate
                await portfolioAPI.choosePortfolio(portfolioId, selectedStrategies);
                id = portfolioId;
            } else if (workflowMode === 'manual') {
                id = await portfolioAPI.selectPool({
                    portfolio_name: portfolioName,
                    account: accountName,
                    strategies: selectedStrategies,
                });
            } else {
                id = await portfolioAPI.aiSelectPool(portfolioName, accountName, aiPrompt);
            }
            setPortfolioId(id);
            handleStepComplete(1);
        } catch {
            toast.error('Failed to create strategy pool');
        } finally {
            setLoadingStep(null);
        }
    };

    const handleStep2Submit = async () => {
        if (!portfolioId) return;
        setLoadingStep(2);
        try {
            let strats: string[];
            if (workflowMode === 'manual') {
                strats = await portfolioAPI.selectPortfolio(portfolioId, selector, selectorK);
            } else {
                strats = await portfolioAPI.aiSelectPortfolio(portfolioId);
            }
            setStrategies(strategies.filter(s => strats.includes(s.strategy_id)));
            setSelectedStrategies([]);
            handleStepComplete(2);
        } catch {
            toast.error('Failed to apply portfolio algorithm');
        } finally {
            setLoadingStep(null);
        }
    };

    const handleStep3Submit = async () => {
        if (!portfolioId) return;
        setLoadingStep(3);
        try {
            await portfolioAPI.choosePortfolio(portfolioId, selectedStrategies);
            handleStepComplete(3);
        } catch {
            toast.error('Failed to confirm strategy selection');
        } finally {
            setLoadingStep(null);
        }
    };

    const handleStep4Submit = async () => {
        if (!portfolioId) return;
        setLoadingStep(4);
        try {
            if (workflowMode !== 'manual') {
                const final = selectedStrategies.map(() => 1);
                setWeights(final);
                await portfolioAPI.seedPortfolio(portfolioId, final);
            } else {
                await portfolioAPI.seedPortfolio(portfolioId, weights);
            }
            handleStepComplete(4);
        } catch {
            toast.error('Failed to set weights');
        } finally {
            setLoadingStep(null);
        }
    };


    // Step 5 state
    const [rebalMethod, setRebalMethod] = useState('score_weighted');
    const [rebalIntervalDays, setRebalIntervalDays] = useState(21);
    const [rebalThreshold, setRebalThreshold] = useState(5);

    const handleStep5Submit = async () => {
        if (!portfolioId) return;
        setLoadingStep(5);
        try {
            await portfolioAPI.createReconcileJob(
                portfolioId,
                rebalIntervalDays * 24 * 60 * 60,
                rebalMethod,
                rebalThreshold / 100,
                true,
            );
            handleStepComplete(5);
            toast.success('Portfolio created successfully');
            router.push(`/portfolios/${portfolioId}`);
        } catch {
            toast.error('Failed to create rebalancing job');
        } finally {
            setLoadingStep(null);
        }
    };

    const toggleStrategy = useCallback((strategyId: string) => {
        setSelectedStrategies(prev =>
            prev.includes(strategyId)
                ? prev.filter(s => s !== strategyId)
                : [...prev, strategyId]
        );
    }, []);

    const handleStepClick = useCallback((step: number) => {
        if (stepStatus[step as keyof typeof stepStatus] !== 'pending') {
            setCurrentStep(step);
        }
    }, [stepStatus]);

    return (
        <ProtectedRoute>
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <div className="bg-white border-b px-6 py-4">
                <div className="flex items-center justify-between max-w-4xl mx-auto">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => router.push('/portfolios')}
                            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 transition-colors"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            Back
                        </button>
                        <div>
                            <h1 className="text-xl font-bold">New Portfolio</h1>
                            <p className="text-sm text-gray-500">Build a meta-portfolio in 5 steps</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-500">Mode:</span>
                        <button
                            onClick={() => setWorkflowMode(prev => prev === 'manual' ? 'automatic' : 'manual')}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 text-sm"
                        >
                            <Settings className="w-3.5 h-3.5" />
                            <span className="font-medium">{workflowMode === 'manual' ? 'Manual' : 'AI-Assisted'}</span>
                            <ChevronDown className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="max-w-4xl mx-auto px-6 py-8">
                <div className="bg-white rounded-lg shadow-sm border p-6 mb-8">
                    <h2 className="text-xl font-bold mb-2">Portfolio Construction Pipeline</h2>
                    <p className="text-gray-600 mb-6">Follow the 5-step workflow to build your meta-portfolio</p>

                    {/* Step 1 */}
                    <StepCard
                        number={1}
                        title="Step 1: Strategy Pool Selection"
                        subtitle="Select or filter initial strategy candidates"
                        icon={Filter}
                        isActive={currentStep === 1}
                        isCompleted={stepStatus[1] === 'completed'}
                        isPending={stepStatus[1] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-4">
                            <input
                                type="text"
                                placeholder="Portfolio Name"
                                value={portfolioName}
                                onChange={(e) => setPortfolioName(e.target.value)}
                                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <input
                                type="text"
                                placeholder="QuantRocket Account (e.g., DU12345)"
                                value={accountName}
                                onChange={(e) => setAccountName(e.target.value)}
                                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />

                            {workflowMode === 'automatic' ? (
                                <textarea
                                    placeholder="AI Prompt (optional) - Describe what kind of strategies you're looking for..."
                                    value={aiPrompt}
                                    onChange={(e) => setAiPrompt(e.target.value)}
                                    className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    rows={3}
                                />
                            ) : (
                                <StrategySelector
                                    strategies={strategies}
                                    selectedStrategies={selectedStrategies}
                                    onToggleStrategy={toggleStrategy}
                                />
                            )}

                            <button
                                onClick={handleStep1Submit}
                                disabled={loadingStep === 1 || !portfolioName || !accountName || (workflowMode === 'manual' && selectedStrategies.length === 0)}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {loadingStep === 1 ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                {loadingStep === 1 ? 'Creating...' : workflowMode === 'manual' ? 'Select Pool' : 'AI Select Pool'}
                            </button>
                        </div>
                    </StepCard>

                    {/* Step 2 */}
                    <StepCard
                        number={2}
                        title="Step 2: Portfolio Algorithm"
                        subtitle="Choose portfolio construction method"
                        icon={Settings}
                        isActive={currentStep === 2}
                        isCompleted={stepStatus[2] === 'completed'}
                        isPending={stepStatus[2] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-3">
                            {workflowMode === 'manual' && (
                                <>
                                    <select
                                        value={selector || ''}
                                        onChange={(e) => setSelector(e.target.value || null)}
                                        className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="">No Selector</option>
                                        <option value="topk">Top K</option>
                                        <option value="bottomk">Bottom K</option>
                                        <option value="ai">AI Selection</option>
                                    </select>
                                    {selector && selector !== 'ai' && (
                                        <input
                                            type="number"
                                            placeholder="K value"
                                            value={selectorK || ''}
                                            onChange={(e) => setSelectorK(e.target.value ? parseInt(e.target.value) : null)}
                                            className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    )}
                                </>
                            )}
                            <button
                                onClick={handleStep2Submit}
                                disabled={loadingStep === 2 || !portfolioId}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {loadingStep === 2 ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                {loadingStep === 2 ? 'Applying...' : workflowMode === 'manual' ? 'Apply Algorithm' : 'AI Select Algorithm'}
                            </button>
                        </div>
                    </StepCard>

                    {/* Step 3 */}
                    <StepCard
                        number={3}
                        title="Step 3: Sub-Portfolio Selection"
                        subtitle="Finalize strategy selection"
                        icon={Shuffle}
                        isActive={currentStep === 3}
                        isCompleted={stepStatus[3] === 'completed'}
                        isPending={stepStatus[3] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-3">
                            <p className="text-sm text-gray-600">Review and finalize your strategy selection</p>
                            <StrategySelector
                                strategies={strategies}
                                selectedStrategies={selectedStrategies}
                                onToggleStrategy={toggleStrategy}
                            />
                            <button
                                onClick={handleStep3Submit}
                                disabled={loadingStep === 3 || !portfolioId || selectedStrategies.length === 0}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                                {loadingStep === 3 ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                {loadingStep === 3 ? 'Confirming...' : 'Confirm Selection'}
                            </button>
                        </div>
                    </StepCard>

                    {/* Step 4 */}
                    <StepCard
                        number={4}
                        title="Step 4: Weight Allocation"
                        subtitle="Assign initial weights to strategies"
                        icon={Sliders}
                        isActive={currentStep === 4}
                        isCompleted={stepStatus[4] === 'completed'}
                        isPending={stepStatus[4] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-3">

                            {workflowMode==='manual' && selectedStrategies.map((strategyId, idx) => {
                                const strategy = strategies.find(s => s.strategy_id === strategyId);
                                return (
                                    <div key={strategyId} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                                        <span className="w-40 text-sm font-medium">{strategy?.name}</span>
                                        <input
                                            type="number"
                                            placeholder="Weight"
                                            value={weights[idx] || ''}
                                            onChange={(e) => {
                                                const newWeights = [...weights];
                                                newWeights[idx] = parseFloat(e.target.value) || 0;
                                                setWeights(newWeights);
                                            }}
                                            className="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                        <span className="text-sm text-gray-600">%</span>
                                    </div>
                                );
                            })}

                            <button
                                onClick={handleStep4Submit}
                                disabled={loadingStep === 4 || !portfolioId || (selectedStrategies.length != weights.length && workflowMode === 'manual')}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {loadingStep === 4 ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                {loadingStep === 4 ? 'Saving...' : 'Set Weights'}
                            </button>
                        </div>
                    </StepCard>

                    {/* Step 5 */}
                    <StepCard
                        number={5}
                        title="Step 5: Rebalancing Schedule"
                        subtitle="Configure automatic rebalancing for this portfolio"
                        icon={RefreshCw}
                        isActive={currentStep === 5}
                        isCompleted={stepStatus[5] === 'completed'}
                        isPending={stepStatus[5] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-3">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs text-gray-500 mb-1 block">Allocation Method</label>
                                    <select
                                        value={rebalMethod}
                                        onChange={e => setRebalMethod(e.target.value)}
                                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="score_weighted">Score Weighted</option>
                                        <option value="equal_weight">Equal Weight</option>
                                        <option value="manual">Manual</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs text-gray-500 mb-1 block">Interval (trading days)</label>
                                    <input
                                        type="number"
                                        min={1}
                                        value={rebalIntervalDays}
                                        onChange={e => setRebalIntervalDays(parseInt(e.target.value) || 21)}
                                        className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs text-gray-500 mb-1 block">Rebalance Threshold (%)</label>
                                <input
                                    type="number"
                                    min={0}
                                    max={100}
                                    step={0.5}
                                    value={rebalThreshold}
                                    onChange={e => setRebalThreshold(parseFloat(e.target.value) || 5)}
                                    className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <p className="text-xs text-gray-400 mt-1">Only rebalance if drift exceeds this threshold</p>
                            </div>
                            <button
                                onClick={handleStep5Submit}
                                disabled={loadingStep === 5 || !portfolioId}
                                className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                {loadingStep === 5 ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                {loadingStep === 5 ? 'Creating...' : 'Create Portfolio'}
                            </button>
                        </div>
                    </StepCard>
                </div>
            </div>
        </div>
        </ProtectedRoute>
    );
}
