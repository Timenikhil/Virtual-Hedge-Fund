'use client';

import React, { useState } from 'react';
import { Check, X } from 'lucide-react';

export interface Strategy {
    strategy_id: string;
    name: string;
    description: string;
    category: string;
    source?: string;
}

interface StrategySelectorProps {
    strategies: Strategy[];
    selectedStrategies: string[];
    onToggleStrategy: (strategyId: string) => void;
}

export const StrategySelector: React.FC<StrategySelectorProps> = ({
                                                                      strategies,
                                                                      selectedStrategies,
                                                                      onToggleStrategy
                                                                  }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('all');

    const categories = ['all', ...new Set(strategies.map(s => s.category))];

    const filteredStrategies = strategies.filter(strategy => {
        const matchesSearch = strategy.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            strategy.description.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = selectedCategory === 'all' || strategy.category === selectedCategory;
        return matchesSearch && matchesCategory;
    });

    return (
        <div className="space-y-3">
            {/* Search and Filter */}
            <div className="flex gap-3">
                <input
                    type="text"
                    placeholder="Search strategies..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    {categories.map(cat => (
                        <option key={cat} value={cat}>
                            {cat === 'all' ? 'All Categories' : cat}
                        </option>
                    ))}
                </select>
            </div>

            {/* Selected Strategies Pills */}
            {selectedStrategies.length > 0 && (
                <div className="flex flex-wrap gap-2 p-3 bg-blue-50 rounded-lg">
          <span className="text-sm font-medium text-gray-700">
            Selected ({selectedStrategies.length}):
          </span>
                    {selectedStrategies.map(stratId => {
                        const strategy = strategies.find(s => s.strategy_id === stratId);
                        return (
                            <span
                                key={stratId}
                                className="inline-flex items-center gap-1 px-3 py-1 bg-blue-600 text-white text-sm rounded-full"
                            >
                {strategy?.name}
                                <button
                                    onClick={() => onToggleStrategy(stratId)}
                                    className="hover:bg-blue-700 rounded-full p-0.5"
                                >
                  <X className="w-3 h-3" />
                </button>
              </span>
                        );
                    })}
                </div>
            )}

            {/* Strategy Cards Grid */}
            <div className="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                {filteredStrategies.map((strategy) => {
                    const isSelected = selectedStrategies.includes(strategy.strategy_id);
                    return (
                        <div
                            key={strategy.strategy_id}
                            onClick={() => onToggleStrategy(strategy.strategy_id)}
                            className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${
                                isSelected
                                    ? 'border-blue-500 bg-blue-50 shadow-md'
                                    : 'border-gray-200 hover:border-blue-300 hover:shadow-sm'
                            }`}
                        >
                            <div className="flex items-start justify-between mb-2">
                                <h4 className="font-semibold text-sm">{strategy.name}</h4>
                                <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                                    isSelected ? 'bg-blue-600 border-blue-600' : 'border-gray-300'
                                }`}>
                                    {isSelected && <Check className="w-3 h-3 text-white" />}
                                </div>
                            </div>
                            <p className="text-xs text-gray-600 mb-2">{strategy.description}</p>
                            <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="inline-block px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                                    {strategy.category}
                                </span>
                                {strategy.source === 'quantrocket' && (
                                    <span className="inline-block px-2 py-1 bg-amber-100 text-amber-700 text-xs rounded font-medium">QR</span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
