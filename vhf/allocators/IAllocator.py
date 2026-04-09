from typing import List

import numpy as np
import pandas as pd
class IAllocator:

    def __init__(self):
        self.prices = None

    """
    This method uses the selected rebalancer to propose the rebalanced portfolio weights.
    This method does NOT update the portfolio weights in the database.
    That is left up to the caller intentionally to reflect the actual portfolio weights
    after attempted rebalancing. (e.g. due to slippage or trans costs, the scheduler obtained a diff
    portfolio distribution in the end)

    Usage :
    1. scheduler is set up
    2. it reads algorithm name from db (or uses cached value)
    3. it calls the rebalance function of the allocator implementing this rebalance function
    with the prices dataframe
    4. the algorithm returns a set of proposed weights
    5. scheduler executes the trade
    6. scheduler updates the portfolio weights in the db

    """
    def rebalance(self,prices:pd.DataFrame) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        """

        :param prices: a 2D dataframe array of shape [time * assets]
        each cell represents a price data point at that time, preferably vwap
        each column represents a separate asset
        each row represents a timestamp

        it is the caller's responsibility to ensure data alignment and integrity
        missing values will be forward filled
        the returned portfolio weights are aligned to the order in the original dataframe
        the timestamps are assumed to be at equal intervals
        :return: weight vector such that sum = 1, and length = prices.shape[1]
        """
        self.prices = prices.ffill().to_numpy()
        pass