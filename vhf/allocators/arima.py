import numpy as np
import pandas as pd
from joblib import load, dump
from scipy.optimize import minimize

from vhf.allocators.IAllocator import IAllocator


class ARIMA(IAllocator):
    """
    Mean-Variance Optimiser that replaces historical expected returns with
    ARIMA next-day forecasts, and blends ARIMA-implied per-asset volatility
    with the historical correlation matrix to form the covariance matrix.

    Covariance construction
    -----------------------
    Rather than running .cov() on raw ARIMA point forecasts (which converge to
    the mean and understate variance), we use:

        Σ = D @ Corr_hist @ D

    where
        Corr_hist  : historical correlation matrix (stable, data-rich estimate
                     of inter-asset co-movement)
        D          : diag(σ_1, …, σ_n), per-asset annualised volatility
                     estimated from the std of the ARIMA multi-step forecast
                     *return* series

    This keeps correlation structure grounded in real data while letting ARIMA
    drive the scale of uncertainty for each asset individually.
    """

    def __init__(self, algo: str = "ARIMA", forecast_horizon: int = 30):
        super().__init__()
        self.prices = None
        self.algo = algo
        self.forecast_horizon = forecast_horizon  # steps for vol estimation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self, sid):
        return load(f"../ai/models/weights/{self.algo}-{sid}.joblib")

    def _save_model(self, model,sid):
        dump(model,f"../ai/models/weights/{self.algo}-{sid}.joblib")
        # if you want to leave old training data unchanged, copy those files elsewhere before starting this up

    def _forecast_returns(self, model, last_price: float) -> np.ndarray:
        """
        Return a daily-return series implied by the ARIMA price forecast.

        model.predict([[n]]) → price forecasts for the next n days
        Prepend last_price so we can compute day-0 → day-1, …, day-(n-1) → day-n.
        """
        price_fc = model.predict([[self.forecast_horizon]])          # shape (horizon,)
        all_prices = np.concatenate([[last_price], price_fc])
        return np.diff(all_prices) / all_prices[:-1]                 # shape (horizon,)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def rebalance(
            self, prices: pd.DataFrame
    ) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        super().rebalance(prices)

        sids = list(prices.columns)
        n = len(sids)
        equal_weights = np.full(n, 1.0 / n, dtype=np.float64)

        try:
            # ── 1. Historical correlation (inter-asset structure) ──────────────
            hist_prices = self.prices.tail(252)
            if len(hist_prices) < 50:
                raise ValueError("Insufficient history — falling back to equal weights")

            hist_returns = hist_prices.pct_change().dropna()
            corr_hist = hist_returns.corr().values           # (n, n)  always PSD

            # ── 2. Per-asset ARIMA forecasts ───────────────────────────────────
            mu = np.empty(n)                   # annualised expected returns
            forecast_vols = np.empty(n)        # annualised forecast volatility

            for i, sid in enumerate(sids):
                model = self._load_model(sid)

                last_price = prices[sid].iloc[-1]
                fc_returns = self._forecast_returns(model, last_price)

                # Next-day expected return, annualised
                mu[i] = fc_returns[0] * 252

                # Per-asset vol: std of the forecast return series, annualised.
                # Falls back to historical vol when ARIMA forecasts are flat
                # (e.g. a pure-AR model that has already converged to its mean).
                fc_vol = fc_returns.std() * np.sqrt(252)
                if fc_vol < 1e-8:
                    fc_vol = hist_returns[sid].std() * np.sqrt(252)
                forecast_vols[i] = fc_vol

                # update model
                model.partial_fit([[1]], np.array([prices[sid].iloc[-1]]))
                self._save_model(model,sid)

            # ── 3. Build covariance matrix: Σ = D @ Corr_hist @ D ─────────────
            D = np.diag(forecast_vols)
            S = D @ corr_hist @ D                            # guaranteed PSD

            # ── 4. Maximise Sharpe (identical machinery to MVO) ───────────────
            def neg_sharpe(w):
                port_ret = w @ mu
                port_vol = np.sqrt(w @ S @ w)
                return -port_ret / port_vol if port_vol > 1e-10 else 1e10

            constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
            bounds = [(0.0, 1.0)] * n

            best_result = None
            for _ in range(20):
                w0 = np.random.dirichlet(np.ones(n))
                res = minimize(
                    neg_sharpe,
                    w0,
                    method="SLSQP",
                    bounds=bounds,
                    constraints=constraints,
                    options={"ftol": 1e-9, "maxiter": 1000},
                )
                if res.success and (best_result is None or res.fun < best_result.fun):
                    best_result = res

            if best_result is None or not best_result.success:
                raise RuntimeError("Optimisation failed — falling back to equal weights")

            # ── 5. Clean and re-normalise ──────────────────────────────────────
            raw = best_result.x
            raw[raw < 1e-4] = 0.0
            total = raw.sum()
            if total <= 0:
                raise RuntimeError("All weights zeroed — falling back to equal weights")

            return np.array(raw / total, dtype=np.float64)

        except Exception:
            return equal_weights