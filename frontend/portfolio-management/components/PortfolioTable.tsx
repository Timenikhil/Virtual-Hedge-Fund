import { Calendar, Layers } from 'lucide-react';
import { useRouter } from 'next/navigation';

interface Portfolio {
    id: number;
    name: string;
    created_at: string;
    strategy_count: number;
    total_value?: number;
    return_percentage?: number;
}

interface PortfolioTableProps {
    portfolios: Portfolio[];
}

export const PortfolioTable: React.FC<PortfolioTableProps> = ({ portfolios }) => {
    const router = useRouter();

    return (
        <div className="bg-white rounded-lg border overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-gray-50 border-b">
                    <tr>
                        <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Portfolio Name</th>
                        <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Created</th>
                        <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Strategies</th>
                        <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Total Value</th>
                        <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Return</th>
                    </tr>
                    </thead>
                    <tbody className="divide-y">
                    {portfolios.map((portfolio) => (
                        <tr
                            key={portfolio.id}
                            onClick={() => router.push(`/portfolios/${portfolio.id}`)}
                            className="hover:bg-gray-50 cursor-pointer transition-colors"
                        >
                            <td className="px-6 py-4">
                                <div className="font-semibold text-gray-900">{portfolio.name}</div>
                            </td>
                            <td className="px-6 py-4">
                                <div className="flex items-center gap-2 text-sm text-gray-600">
                                    <Calendar className="w-4 h-4" />
                                    {new Date(portfolio.created_at).toLocaleDateString()}
                                </div>
                            </td>
                            <td className="px-6 py-4">
                                <div className="flex items-center gap-2">
                                    <Layers className="w-4 h-4 text-gray-400" />
                                    <span className="font-medium">{portfolio.strategy_count}</span>
                                </div>
                            </td>
                            <td className="px-6 py-4">
                                <div className="font-medium">${(portfolio.total_value || 0).toLocaleString()}</div>
                            </td>
                            <td className="px-6 py-4">
                                <div className={`inline-flex px-3 py-1 rounded-full text-sm font-medium ${
                                    (portfolio.return_percentage || 0) >= 0
                                        ? 'bg-green-100 text-green-700'
                                        : 'bg-red-100 text-red-700'
                                }`}>
                                    {(portfolio.return_percentage || 0) >= 0 ? '+' : ''}
                                    {portfolio.return_percentage?.toFixed(1)}%
                                </div>
                            </td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};