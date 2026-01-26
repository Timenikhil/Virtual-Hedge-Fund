'use client';

import React from 'react';
import { LucideIcon, Check, Activity, Clock } from 'lucide-react';

interface StepCardProps {
    number: number;
    title: string;
    subtitle: string;
    icon: LucideIcon;
    isActive: boolean;
    isCompleted: boolean;
    isPending: boolean;
    onStepClick: (step: number) => void;
    children?: React.ReactNode;
}

export const StepCard: React.FC<StepCardProps> = ({
                                                      number,
                                                      title,
                                                      subtitle,
                                                      icon: Icon,
                                                      isActive,
                                                      isCompleted,
                                                      isPending,
                                                      onStepClick,
                                                      children
                                                  }) => {
    const isClickable = !isPending;

    return (
        <div className="mb-4">
            <div
                className={`border rounded-lg p-6 transition-all ${
                    isActive ? 'border-blue-500 bg-white shadow-lg' :
                        isCompleted ? 'border-green-500 bg-green-50' :
                            'border-gray-200 bg-gray-50'
                } ${isClickable ? 'cursor-pointer hover:shadow-md' : 'cursor-not-allowed opacity-60'}`}
                onClick={() => isClickable && onStepClick(number)}
            >
                <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4 flex-1">
                        <div className={`p-3 rounded-lg ${
                            isActive ? 'bg-blue-100' :
                                isCompleted ? 'bg-green-100' :
                                    'bg-gray-200'
                        }`}>
                            <Icon className={`w-6 h-6 ${
                                isActive ? 'text-blue-600' :
                                    isCompleted ? 'text-green-600' :
                                        'text-gray-500'
                            }`} />
                        </div>
                        <div className="flex-1">
                            <h3 className="text-lg font-semibold mb-1">{title}</h3>
                            <p className="text-gray-600 text-sm">{subtitle}</p>
                            {isActive && children}
                        </div>
                    </div>
                    <div>
                        {isCompleted ? (
                            <Check className="w-6 h-6 text-green-600" />
                        ) : isActive ? (
                            <Activity className="w-6 h-6 text-blue-600" />
                        ) : (
                            <Clock className="w-6 h-6 text-gray-400" />
                        )}
                    </div>
                </div>
            </div>
            {number < 5 && (
                <div className="flex justify-center my-2">
                    <div className={`w-0.5 h-8 ${isCompleted ? 'bg-green-500' : 'bg-gray-300'}`} />
                </div>
            )}
        </div>
    );
};