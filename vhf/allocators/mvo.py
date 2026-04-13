import numpy as np
import pandas as pd
from scipy.optimize import minimize

from vhf.allocators.IAllocator import IAllocator


class MVO(IAllocator):

    def __init__(self):
        super().__init__()
        self.prices = None

    def rebalance(self, prices: pd.DataFrame) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        super().rebalance(prices)
        try:
            hist_prices = self.prices.tail(252)  # Use last year of data
            if len(hist_prices) < 50:
                raise Exception("Fallback to equal weights")

            # --- Compute expected returns (annualised mean historical return) ---
            daily_returns = hist_prices.pct_change().dropna()
            mu = daily_returns.mean().values * 252  # annualise

            # --- Compute sample covariance matrix (annualised) ---
            S = daily_returns.cov().values * 252

            n = len(mu)

            # --- Maximise Sharpe Ratio via minimising negative Sharpe ---
            # Sharpe = (w @ mu - rf) / sqrt(w @ S @ w), rf = 0
            def neg_sharpe(w):
                port_return = w @ mu
                port_vol = np.sqrt(w @ S @ w)
                return -port_return / port_vol if port_vol > 1e-10 else 1e10

            # Constraints: weights sum to 1
            constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

            # Bounds: no shorting (0 <= w <= 1)
            bounds = [(0.0, 1.0)] * n

            # Try multiple random starting points to avoid local minima
            best_result = None
            for _ in range(20):
                w0 = np.random.dirichlet(np.ones(n))  # random weights summing to 1
                result = minimize(
                    neg_sharpe,
                    w0,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=constraints,
                    options={"ftol": 1e-9, "maxiter": 1000},
                )
                if result.success and (best_result is None or result.fun < best_result.fun):
                    best_result = result

            if best_result is None or not best_result.success:
                raise Exception("Optimisation failed, fallback to equal weights")

            # --- Clean weights (zero out negligible positions) ---
            raw_weights = best_result.x
            raw_weights[raw_weights < 1e-4] = 0.0
            total = raw_weights.sum()
            if total <= 0:
                raise Exception("All weights zeroed, fallback to equal weights")
            cleaned_weights = raw_weights / total  # re-normalise after cleaning

            return np.array(cleaned_weights, dtype=np.float64)

        except Exception as e:
            assets = prices.shape[1]
            weights = [(1.0 / assets)] * assets
            return np.array(weights, dtype=np.float64)




