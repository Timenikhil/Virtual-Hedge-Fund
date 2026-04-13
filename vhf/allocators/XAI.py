import numpy as np
import pandas as pd
from joblib import load, dump
from scipy.optimize import minimize
from copy import deepcopy

from vhf.allocators.IAllocator import IAllocator


class XAI(IAllocator):
    """
    Mean-Variance Forecasting Optimiser that replaces historical expected returns with
    XAI next-day forecasts, and blends XAI-implied per-asset volatility
    with the historical correlation matrix to form the covariance matrix.

    Covariance construction
    -----------------------
    Rather than running .cov() on raw XAI point forecasts (which converge to
    the mean and understate variance), we use:

        Σ = D @ Corr_hist @ D

    where
        Corr_hist  : historical correlation matrix (stable, data-rich estimate
                     of inter-asset co-movement)
        D          : diag(σ_1, …, σ_n), per-asset annualised volatility
                     estimated from the std of the XAI multi-step forecast
                     *return* series

    This keeps correlation structure grounded in real data while letting XAI
    drive the scale of uncertainty for each asset individually.
    """

    def __init__(
            self,
            algo: str = "XAI",
            forecast_horizon: int = 30,
            alpha1: float = 1.0,       # weight on portfolio variance term
            alpha2: float = 1.0,       # weight on expected return term
            alpha3: float = 0.5,       # weight on model uncertainty (RMSE) term
            lambda_tc: float = 0.005,  # per-asset transaction cost weight
            error_window: int = 5,     # h: number of recent days used to compute ε̄_i
    ):
        super().__init__()
        self.prices = None
        self.algo = algo
        self.forecast_horizon = forecast_horizon
        self.alpha1 = alpha1
        self.alpha2 = alpha2
        self.alpha3 = alpha3
        self.lambda_tc = lambda_tc
        self.error_window = error_window
        self.prev_weights: np.ndarray | None = None  # w_{i,0} for transaction cost term

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
        Return a daily-return series implied by the XAI log return forecast.

        model.predict([[n]]) → price forecasts for the next n days
        """

        all_prices = []
        model = deepcopy(model)

        for i in range(self.forecast_horizon):
            price_fc = model.predict()
            all_prices.extend(price_fc)
            model.partial_fit(None, [price_fc])

        all_prices = np.ndarray(all_prices)

        return (np.e ** all_prices) - 1  # shape (horizon,)

    def _calc_epsilon(self, model, hist_prices_h: np.ndarray) -> float:
        """
        Compute per-asset model RMSE (ε̄_i) over the last `error_window` days.

        Walk-forward on actual historical prices: at each step predict the next
        price, record the error against the true price, then update the model
        with the true price before moving on.  This isolates genuine prediction
        error from forecast-distribution spread.

        hist_prices_h : 1-D array of the last h actual prices for this asset.
        """
        model = deepcopy(model)
        errors = []
        for actual in hist_prices_h:
            forecast = model.predict()[0]
            errors.append(actual - forecast)
            model.partial_fit(actual)
        return float(np.sqrt(np.mean(np.array(errors) ** 2)))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def rebalance(
            self, prices: pd.DataFrame,trans_cost = 0.005
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

            # ── 2. Per-asset XAI forecasts ───────────────────────────────────
            mu = np.empty(n)                   # annualised expected returns
            forecast_vols = np.empty(n)        # annualised forecast volatility
            epsilons = np.empty(n)             # per-asset model uncertainty (RMSE proxy, §9.6)

            for i, sid in enumerate(sids):
                model = self._load_model(sid)

                last_price = prices[sid].iloc[-1]
                fc_returns = self._forecast_returns(model, last_price)

                # Next-day expected return, annualised
                mu[i] = fc_returns[0] * 252

                # Per-asset vol: std of the forecast return series, annualised.
                # Falls back to historical vol when XAI forecasts are flat
                # (e.g. a pure-AR model that has already converged to its mean).
                fc_vol = fc_returns.std() * np.sqrt(252)
                if fc_vol < 1e-8:
                    fc_vol = hist_returns[sid].std() * np.sqrt(252)
                forecast_vols[i] = fc_vol

                # Per-asset uncertainty ε̄_i: walk-forward RMSE over last h days (§9.6)
                hist_h = self.prices[sid].values[-(self.error_window + 1):]
                epsilons[i] = self._calc_epsilon(model, hist_h)

                # update model
                model.partial_fit([[1]], np.array([prices[sid].iloc[-1]]))
                self._save_model(model,sid)

            # ── 3. Build covariance matrix: Σ = D @ Corr_hist @ D ─────────────
            D = np.diag(forecast_vols)
            S = D @ corr_hist @ D                            # guaranteed PSD

            # ── 4. MVF objective: min ½α₁wᵀΣw − α₂wᵀμ + α₃wᵀε + λ|w − w₀| ──
            # term 1: portfolio variance (risk)
            # term 2: expected return (negative → maximise)
            # term 3: model uncertainty penalty — penalises assets the XAI
            #         model is least confident about (high RMSE → avoid)
            # term 4: transaction cost — penalises large turnover from w_prev
            # Note: |w − w₀| is kept as-is; a proper convex formulation would
            # linearise via auxiliary buy/sell variables (see §9.6), but scipy
            # SLSQP handles the non-smooth term adequately in practice.
            w_prev = self.prev_weights if self.prev_weights is not None else equal_weights

            def mvf_objective(w):
                variance    = 0.5 * self.alpha1 * (w @ S @ w)
                exp_return  = self.alpha2 * (w @ mu)
                uncertainty = self.alpha3 * (w @ epsilons)
                trans_cost  = self.lambda_tc * np.sum(np.abs(w - w_prev))
                return variance - exp_return + uncertainty + trans_cost

            constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
            bounds = [(0.0, 1.0)] * n

            best_result = None
            for _ in range(20):
                w0 = np.random.dirichlet(np.ones(n))
                res = minimize(
                    mvf_objective,
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

            final_weights = np.array(raw / total, dtype=np.float64)
            self.prev_weights = final_weights   # persist for next rebalance's transaction cost
            return final_weights

        except Exception:
            return equal_weights