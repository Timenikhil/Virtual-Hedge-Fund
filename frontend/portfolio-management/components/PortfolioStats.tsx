import { Briefcase, Layers, TrendingUp } from 'lucide-react';

interface Portfolio {
    strategy_count: number;
    return_percentage?: number;
}

interface PortfolioStatsProps {
    portfolios: Portfolio[];
}

export const PortfolioStats: React.FC<PortfolioStatsProps> = ({ portfolios }) => {
    const avgReturn = portfolios.length > 0
        ? (portfolios.reduce((sum, p) => sum + (p.return_percentage || 0), 0) / portfolios.length).toFixed(1)
        : '0.0';

    return (
        <div className="grid grid-cols-3 gap-6 mb-8">
            <div className="bg-white p-6 rounded-lg border shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                    <Briefcase className="w-5 h-5 text-blue-600" />
                    <span className="text-sm text-gray-600">Total Portfolios</span>
                </div>
                <div className="text-3xl font-bold">{portfolios.length}</div>
            </div>
            <div className="bg-white p-6 rounded-lg border shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                    <Layers className="w-5 h-5 text-green-600" />
                    <span className="text-sm text-gray-600">Total Strategies</span>
                </div>
                <div className="text-3xl font-bold">
                    {portfolios.reduce((sum, p) => sum + p.strategy_count, 0)}
                </div>
            </div>
            <div className="bg-white p-6 rounded-lg border shadow-sm">
                <div className="flex items-center gap-3 mb-2">
                    <TrendingUp className="w-5 h-5 text-purple-600" />
                    <span className="text-sm text-gray-600">Avg Return</span>
                </div>
                <div className="text-3xl font-bold">{avgReturn}%</div>
            </div>
        </div>
    );
};