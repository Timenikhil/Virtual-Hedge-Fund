'use client';

import React, { useState, useCallback } from 'react';
import { Filter, Settings, Shuffle, Sliders, RefreshCw, ChevronDown, Play } from 'lucide-react';
import { portfolioAPI } from '@/lib/api';
import { StrategySelector, Strategy } from '@/components/StrategySelector';
import { StepCard } from '@/components/StepCard';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import {useRouter} from "next/navigation";

// const INITIAL_STRATEGIES: Strategy[] = [
//     { id: 'strat-1', name: 'Momentum Strategy', description: 'Trend-following based on price momentum', category: 'Trend' },
//     { id: 'strat-2', name: 'Mean Reversion', description: 'Statistical arbitrage on price reversals', category: 'Statistical' },
//     { id: 'strat-3', name: 'Value Investing', description: 'Fundamental analysis based approach', category: 'Fundamental' },
//     { id: 'strat-4', name: 'Market Making', description: 'Spread capture and liquidity provision', category: 'Arbitrage' },
//     { id: 'strat-5', name: 'Pairs Trading', description: 'Correlated asset arbitrage', category: 'Statistical' },
//     { id: 'strat-6', name: 'Options Strategy', description: 'Volatility and delta-neutral strategies', category: 'Derivatives' },
//     { id: 'strat-7', name: 'Machine Learning', description: 'AI-driven predictive models', category: 'Quantitative' },
//     { id: 'strat-8', name: 'Risk Parity', description: 'Equal risk contribution allocation', category: 'Risk-Based' },
// ];

const INITIAL_STRATEGIES = await portfolioAPI.getStrategies();

export default function PortfolioManagement() {
    const router = useRouter();
    const [workflowMode, setWorkflowMode] = useState<'manual' | 'automatic'>('manual');
    const [currentStep, setCurrentStep] = useState(1);
    const [portfolioName, setPortfolioName] = useState('');
    const [portfolioId, setPortfolioId] = useState<number | null>(null);
    const [strategies, setStrategies] = useState<Strategy[]>(INITIAL_STRATEGIES);
    const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
    const [aiPrompt, setAiPrompt] = useState('');
    const [selector, setSelector] = useState<string | null>('topk');
    const [selectorK, setSelectorK] = useState<number | null>(10);
    const [weights, setWeights] = useState<number[]>([]);

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
        try {
            let id: number;
            if (workflowMode === 'manual') {
                id = await portfolioAPI.selectPool({
                    portfolio_name: portfolioName,
                    strategies: selectedStrategies
                });
            } else {
                id = await portfolioAPI.aiSelectPool(portfolioName, aiPrompt);
            }
            setPortfolioId(id);
            handleStepComplete(1);
        } catch (error) {
            console.error('Error in Step 1:', error);
        }
    };

    const handleStep2Submit = async () => {
        if (!portfolioId) return;
        try {
            let strats : string[]
            if (workflowMode === 'manual') {
                strats = await portfolioAPI.selectPortfolio(portfolioId, selector, selectorK);
            } else {
                strats = await portfolioAPI.aiSelectPortfolio(portfolioId);
            }
            setStrategies(strategies.filter(s => strats.includes(s.strategy_id)));
            setSelectedStrategies([]); // Reset selections for Step 3
            handleStepComplete(2);
        } catch (error) {
            console.error('Error in Step 2:', error);
        }
    };

    const handleStep3Submit = async () => {
        if (!portfolioId) return;
        try {
            await portfolioAPI.choosePortfolio(portfolioId,selectedStrategies);
            handleStepComplete(3);
        } catch (error) {
            console.error('Error in Step 3:', error);
        }
    };

    const handleStep4Submit = async () => {
        if (!portfolioId) return;
        try {
            await portfolioAPI.seedPortfolio(portfolioId, weights);
            handleStepComplete(4);
        } catch (error) {
            console.error('Error in Step 4:', error);
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
                <div className="flex items-center justify-between max-w-6xl mx-auto">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <div className="p-2 bg-blue-100 rounded">
                                <Sliders className="w-5 h-5 text-blue-600" />
                            </div>
                            <h1 className="text-2xl font-bold">Portfolio Management</h1>
                        </div>
                        <p className="text-gray-600">Build and manage meta-portfolios with AI assistance</p>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-600">Workflow Mode:</span>
                        <button
                            onClick={() => setWorkflowMode(prev => prev === 'manual' ? 'automatic' : 'manual')}
                            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                        >
                            <Settings className="w-4 h-4" />
                            <span className="font-medium">{workflowMode === 'manual' ? 'Manual' : 'Automatic'}</span>
                            <ChevronDown className="w-4 h-4" />
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
                                disabled={!portfolioName || (workflowMode === 'manual' && selectedStrategies.length === 0)}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                <Play className="w-4 h-4" />
                                {workflowMode === 'manual' ? 'Select Pool' : 'AI Select Pool'}
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
                                disabled={!portfolioId}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            >
                                <Play className="w-4 h-4" />
                                {workflowMode === 'manual' ? 'Apply Algorithm' : 'AI Select Algorithm'}
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
                                disabled={ !portfolioId || selectedStrategies.length === 0}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                                <Play className="w-4 h-4" />
                                Confirm Selection
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
                            {selectedStrategies.map((strategyId, idx) => {
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
                                disabled={!portfolioId}
                                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                            >
                                Set Weights
                            </button>
                        </div>
                    </StepCard>

                    {/* Step 5 */}
                    <StepCard
                        number={5}
                        title="Step 5: Rebalancing Strategy"
                        subtitle="Configure live portfolio rebalancing"
                        icon={RefreshCw}
                        isActive={currentStep === 5}
                        isCompleted={stepStatus[5] === 'completed'}
                        isPending={stepStatus[5] === 'pending'}
                        onStepClick={handleStepClick}
                    >
                        <div className="mt-4 space-y-3">
                            <p className="text-sm text-gray-600">Configure automatic rebalancing rules</p>
                            <button
                                onClick={() => router.push(`/portfolios/${portfolioId}`)}
                                disabled={!portfolioId}
                                className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                            >
                                Complete Setup
                            </button>
                        </div>
                    </StepCard>
                </div>
            </div>
        </div>
        </ProtectedRoute>
    );
}