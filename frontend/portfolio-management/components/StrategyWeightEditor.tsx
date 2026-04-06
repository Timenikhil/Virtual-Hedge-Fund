import { useState, useEffect } from 'react';
import { portfolioAPI } from '@/lib/api';

interface Strategy {
    id: string;
    name: string;
    weight: number;
}

interface StrategyWeightEditorProps {
    portfolioId: number;
    strategies: Strategy[];
    colors: string[];
    onWeightsUpdated?: () => void;
}

export default function StrategyWeightEditor({
                                                 portfolioId,
                                                 strategies,
                                                 colors,
                                                 onWeightsUpdated
                                             }: StrategyWeightEditorProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [editedWeights, setEditedWeights] = useState<number[]>([]);
    const [isSaving, setIsSaving] = useState(false);

    // Initialize edited weights when strategies load
    useEffect(() => {
        setEditedWeights(strategies.map(s => s.weight));
    }, [strategies]);

    const handleWeightChange = (index: number, value: string) => {
        const newWeights = [...editedWeights];
        newWeights[index] = parseFloat(value) || 0;
        setEditedWeights(newWeights);
    };

    const handleSaveWeights = async () => {
        setIsSaving(true);
        try {
            await portfolioAPI.seedPortfolio(portfolioId, editedWeights);
            setIsEditing(false);

            // Call callback to refresh parent data
            if (onWeightsUpdated) {
                onWeightsUpdated();
            }
        } catch (error) {
            console.error('Failed to update weights:', error);
            alert('Failed to update weights');
        } finally {
            setIsSaving(false);
        }
    };

    const handleCancel = () => {
        setEditedWeights(strategies.map(s => s.weight));
        setIsEditing(false);
    };

    const totalWeight = editedWeights.reduce((sum, w) => sum + w, 0);
    const isValidWeights = Math.abs(totalWeight - 100) < 0.01;

    return (
        <div className="bg-white rounded-lg border p-6">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">Strategies</h2>
                {!isEditing ? (
                    <button
                        onClick={() => setIsEditing(true)}
                        className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                    >
                        Edit Weights
                    </button>
                ) : (
                    <div className="flex gap-2">
                        <button
                            onClick={handleCancel}
                            className="px-4 py-2 text-sm bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                            disabled={isSaving}
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSaveWeights}
                            className="px-4 py-2 text-sm bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
                            disabled={!isValidWeights || isSaving}
                        >
                            {isSaving ? 'Saving...' : 'Save'}
                        </button>
                    </div>
                )}
            </div>

            {isEditing && (
                <div className={`mb-3 p-2 rounded ${isValidWeights ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    Total: {totalWeight.toFixed(1)}% {isValidWeights ? '✓' : '(must equal 100%)'}
                </div>
            )}

            <div className="space-y-3">
                {strategies.map((strategy, index) => (
                    <div
                        key={strategy.id}
                        className={`flex items-center justify-between p-3 rounded-lg ${
                            isEditing ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50'
                        }`}
                    >
                        <div className="flex items-center gap-3">
                            <div
                                className="w-4 h-4 rounded"
                                style={{ backgroundColor: colors[index % colors.length] }}
                            />
                            <span className="font-medium">{strategy.name}</span>
                        </div>

                        {isEditing ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="number"
                                    value={editedWeights[index]}
                                    onChange={(e) => handleWeightChange(index, e.target.value)}
                                    className="w-20 px-2 py-1 border rounded text-right"
                                    step="0.1"
                                    min="0"
                                    max="100"
                                />
                                <span className="text-lg font-semibold">%</span>
                            </div>
                        ) : (
                            <span className="text-lg font-semibold">{strategy.weight.toFixed(2)}%</span>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}