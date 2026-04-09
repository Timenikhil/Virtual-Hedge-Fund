import numpy as np
import pandas as pd

from vhf.allocators.IAllocator import IAllocator


class Equal(IAllocator):

    def __init__(self):
        super().__init__()
        self.prices = None

    def rebalance(self,prices:pd.DataFrame) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        assets =  prices.shape[1]
        weights = [(1.0/assets)] * assets
        return np.array(weights, dtype=np.float64)

