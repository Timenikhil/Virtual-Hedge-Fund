import { Briefcase, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';

interface EmptyPortfolioStateProps {
    hasPortfolios: boolean;
}

export const EmptyPortfolioState: React.FC<EmptyPortfolioStateProps> = ({ hasPortfolios }) => {
    const router = useRouter();

    return (
        <div className="bg-white rounded-lg border p-12 text-center">
            <Briefcase className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-xl font-semibold mb-2">
                {hasPortfolios ? 'No portfolios match your filters' : 'No portfolios yet'}
            </h3>
            <p className="text-gray-600 mb-6">
                {hasPortfolios
                    ? 'Try adjusting your search or filters'
                    : 'Create your first meta-portfolio to get started'}
            </p>
            {!hasPortfolios && (
                <button
                    onClick={() => router.push('/portfolios/create')}
                    className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                    <Plus className="w-5 h-5" />
                    Create Portfolio
                </button>
            )}
        </div>
    );
};