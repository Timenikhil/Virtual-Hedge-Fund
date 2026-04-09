'use client';

import { useRouter } from 'next/navigation';
import { TrendingUp, TrendingDown, Radio } from 'lucide-react';

interface Portfolio {
    id: number;
    name: string;
    created_at: string;
    strategy_count: number;
    strategy_names?: string[];
    total_value?: number;
    return_percentage?: number;
    live?: boolean;
}

interface PortfolioTableProps {
    portfolios: Portfolio[];
}

export const PortfolioTable: React.FC<PortfolioTableProps> = ({ portfolios }) => {
    const router = useRouter();

    return (
        <div className="grid gap-3">
            {portfolios.map(portfolio => {
                const ret = portfolio.return_percentage ?? 0;
                const positive = ret >= 0;
                return (
                    <div
                        key={portfolio.id}
                        onClick={() => router.push(`/portfolios/${portfolio.id}`)}
                        className="bg-white rounded-lg border hover:border-indigo-300 hover:shadow-sm cursor-pointer transition-all px-6 py-4 flex items-center gap-6"
                    >
                        {/* Name + badges */}
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                                <span className="font-semibold text-gray-900 truncate">{portfolio.name}</span>
                                {portfolio.live && (
                                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
                                        <Radio className="w-3 h-3" />
                                        Live
                                    </span>
                                )}
                                {!portfolio.live && (
                                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
                                        Paper
                                    </span>
                                )}
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {(portfolio.strategy_names ?? []).map(name => (
                                    <span key={name} className="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-600">
                                        {name}
                                    </span>
                                ))}
                            </div>
                        </div>

                        {/* Created date */}
                        <div className="text-sm text-gray-400 whitespace-nowrap hidden md:block">
                            {new Date(portfolio.created_at).toLocaleDateString()}
                        </div>

                        {/* Return */}
                        <div className={`flex items-center gap-1.5 text-sm font-semibold whitespace-nowrap px-3 py-1.5 rounded-lg ${
                            positive ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                        }`}>
                            {positive
                                ? <TrendingUp className="w-4 h-4" />
                                : <TrendingDown className="w-4 h-4" />
                            }
                            {positive ? '+' : ''}{ret.toFixed(1)}%
                        </div>
                    </div>
                );
            })}
        </div>
    );
};
