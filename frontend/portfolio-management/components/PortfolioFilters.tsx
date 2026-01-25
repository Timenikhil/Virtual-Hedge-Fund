interface PortfolioFiltersProps {
    searchQuery: string;
    setSearchQuery: (value: string) => void;
    filterStrategyCount: string;
    setFilterStrategyCount: (value: string) => void;
    filterMinValue: string;
    setFilterMinValue: (value: string) => void;
}

export const PortfolioFilters: React.FC<PortfolioFiltersProps> = ({
                                                                      searchQuery,
                                                                      setSearchQuery,
                                                                      filterStrategyCount,
                                                                      setFilterStrategyCount,
                                                                      filterMinValue,
                                                                      setFilterMinValue
                                                                  }) => {
    return (
        <div className="bg-white rounded-lg border p-4 mb-6">
            <div className="grid grid-cols-3 gap-4">
                <input
                    type="text"
                    placeholder="Search portfolios..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                    type="number"
                    placeholder="Min strategies"
                    value={filterStrategyCount}
                    onChange={(e) => setFilterStrategyCount(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <input
                    type="number"
                    placeholder="Min value ($)"
                    value={filterMinValue}
                    onChange={(e) => setFilterMinValue(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
        </div>
    );
};