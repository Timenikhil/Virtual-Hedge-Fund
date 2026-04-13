"""
Regime-Aware XAI Forecaster
============================
Implements the architecture from Chapter 7 / 9 of the FYP report:

    Training
    --------
    1. Engineer CJM features (log-return + rolling vol) from price series.
    2. Fit CJM on training features → hard regime labels + soft proba.
    3. For each regime r  →  train one ARIMA+LSSVM expert on regime-filtered prices.
    4. Train one SharedExpert on the full price series (fallback during transitions).

    Inference
    ---------
    1. CJM.predict_proba_online() → probability vector p  (shape: n_regimes,)
    2. Each expert produces (forecast, rmse_error).
    3. MoE aggregation:
           q   = expert quality weights (inverse-error, softmax-normalised)
           out = q · Σ(p_i · Expert_i(x))  +  (1-q) · SharedExpert(x)
    4. Return combined one-step-ahead price forecast.

Notes
-----
- MVF portfolio layer is intentionally excluded (separate component).
- ARIMA hyperparameters are locked after training (no re-search at inference).
- partial_fit() updates ARIMA + LSSVM online as new observations arrive.
"""

import numpy as np
import pandas as pd
import pmdarima as pm
from joblib import dump, load
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_array, check_is_fitted
from jumpmodels.jump import JumpModel
from jumpmodels.preprocess import DataClipper, DataScaler

from vhf.ai.models.lssvm import LSSVM


# ──────────────────────────────────────────────────────────────────────────────
# Feature engineering
# ──────────────────────────────────────────────────────────────────────────────

def _make_cjm_features(prices: pd.Series, vol_windows=(5, 21, 63)) -> pd.DataFrame:
    """
    Build CJM input features from a raw price series.

    Features (per report §8.3 / §8.4):
        log_ret       – log return (stationary, time-additive)
        vol_{w}       – rolling std of log returns at each window in vol_windows

    Returns a DataFrame aligned to the price index with leading NaNs dropped.
    """
    log_ret = np.log(prices / prices.shift(1))
    feats = {"log_ret": log_ret}
    for w in vol_windows:
        feats[f"vol_{w}"] = log_ret.rolling(w).std()
    return pd.DataFrame(feats, index=prices.index).dropna()


# ──────────────────────────────────────────────────────────────────────────────
# Single Expert: ARIMA + LSSVM
# ──────────────────────────────────────────────────────────────────────────────

class _Expert:
    """
    One ARIMA + LSSVM expert specialised to a single market regime (§9.5).

    ARIMA  captures linear dependencies in the price series.
    LSSVM  captures non-linear dependencies in the ARIMA residuals.

    Combined forecast:  ŷ_t = f̂_t (ARIMA)  +  ε̂_t (LSSVM)

    Parameters
    ----------
    lookback : int
        Number of past ARIMA residuals fed as lagged features to LSSVM.
    error_window : int
        Rolling window (in trading days) for computing per-expert RMSE,
        used by the MoE router as the quality weight q.
    """

    def __init__(self, lookback: int = 10, error_window: int = 21):
        self.lookback = lookback
        self.error_window = error_window

        self.arima_: pm.ARIMA | None = None
        self._residual_buf: list[float] = []   # circular buffer of past residuals
        self._error_buf: list[float] = []       # rolling forecast errors for RMSE

        self.lssvm_: LSSVM | None = None

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(self, prices: np.ndarray) -> "_Expert":
        """
        Fit ARIMA on prices, then fit LSSVM on the in-sample residuals.

        Walk-forward residuals are used so that each residual is computed
        from a one-step-ahead forecast given only past data (no leakage).
        """
        if len(prices) < self.lookback + 5:
            # Insufficient regime data — mark as untrained; MoE will skip.
            return self

        # --- Step 1: fit AutoARIMA (hyperparams locked after this) -----------
        self.arima_ = pm.auto_arima(
            prices,
            information_criterion="aic",   # AIC preferred over BIC (§9.3)
            stepwise=True,
            error_action="ignore",
            suppress_warnings=True,
        )

        # --- Step 2: walk-forward in-sample residuals  -----------------------
        # Re-fit with update() to get causal one-step residuals.
        # We initialise a fresh model with the same (p,d,q) order so that
        # auto_arima's hyperparameter search does not run again at inference.
        order = self.arima_.order
        seasonal_order = self.arima_.seasonal_order

        residuals = []
        # Warm-up: use first `lookback` points to initialise a rolling model
        warm_model = pm.ARIMA(order=order, seasonal_order=seasonal_order)
        warm_model.fit(prices[: self.lookback])

        for t in range(self.lookback, len(prices)):
            pred = warm_model.predict(n_periods=1)[0]
            residuals.append(prices[t] - pred)
            warm_model.update([prices[t]])

        residuals = np.array(residuals)
        self._residual_buf = list(residuals[-self.lookback:])

        # --- Step 3: fit LSSVM on lagged residuals ---------------------------
        # Input:  [ε_{t-lookback}, …, ε_{t-1}]
        # Target: ε_t
        X_res, y_res = self._lag_matrix(residuals, self.lookback)
        self.lssvm_ = LSSVM(lookback_period=self.lookback)
        self.lssvm_.fit(X_res, y_res)

        return self

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self) -> tuple[float, float]:
        """
        Produce a one-step-ahead forecast and the expert's current RMSE.

        Returns
        -------
        forecast : float   – combined ARIMA + LSSVM prediction
        rmse     : float   – rolling RMSE over past `error_window` steps
        """
        if self.arima_ is None or self.lssvm_ is None:
            return 0.0, float("inf")   # untrained expert; MoE weight → 0

        arima_fc = self.arima_.predict(n_periods=1)[0]

        lssvm_input = np.array(self._residual_buf[-self.lookback:]).reshape(1, -1)
        residual_fc = self.lssvm_.predict(lssvm_input)[0]

        forecast = arima_fc + residual_fc
        rmse = self._rolling_rmse()
        return forecast, rmse

    # ── Online update  ────────────────────────────────────────────────────────

    def update(self, actual: float) -> None:
        """
        Ingest one new observation.  Updates ARIMA state, residual buffer,
        LSSVM, and rolling error tracker.
        """
        if self.arima_ is None:
            return

        # Compute error against last forecast before updating
        arima_fc = self.arima_.predict(n_periods=1)[0]
        residual = actual - arima_fc
        self._error_buf.append(abs(residual))
        if len(self._error_buf) > self.error_window:
            self._error_buf.pop(0)

        # Update ARIMA state
        self.arima_.update([actual])

        # Update residual buffer
        self._residual_buf.append(residual)
        if len(self._residual_buf) > self.lookback:
            self._residual_buf.pop(0)

        # Online LSSVM update (if supported)
        if hasattr(self.lssvm_, "partial_fit") and len(self._residual_buf) == self.lookback:
            x = np.array(self._residual_buf[:-1]).reshape(1, -1)
            y = np.array([self._residual_buf[-1]])
            self.lssvm_.partial_fit(x, y)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _rolling_rmse(self) -> float:
        if not self._error_buf:
            return float("inf")
        return float(np.sqrt(np.mean(np.array(self._error_buf) ** 2)))

    @staticmethod
    def _lag_matrix(series: np.ndarray, lags: int):
        """Build supervised (X, y) from a 1-D series with `lags` lag features."""
        X = np.array([series[i: i + lags] for i in range(len(series) - lags)])
        y = series[lags:]
        return X, y


# ──────────────────────────────────────────────────────────────────────────────
# Mixture of Experts router
# ──────────────────────────────────────────────────────────────────────────────

def _moe_aggregate(
        regime_probs: np.ndarray,
        expert_forecasts: np.ndarray,
        expert_rmses: np.ndarray,
        shared_forecast: float,
        top_k: int = 2,
        c: float = 1.0,
) -> float:
    """
    MoE aggregation (§9.2, §10) with top-k expert selection:

        1. Select the top-k experts by CJM regime probability.
        2. Within those k experts compute quality scalar q:
               q = Σ(c / rmse_i · p_i) / Σ(c / rmse_i)   ∈ [0, 1]
           where c is a tunable scale constant (default 1.0).
        3. Aggregate:
               out = q · Σ_k(p_i · Expert_i(x))  +  (1−q) · SharedExpert(x)
           where probabilities are re-normalised over the top-k subset.

    Parameters
    ----------
    regime_probs     : CJM probability vector             (n_regimes,)
    expert_forecasts : per-expert one-step forecast       (n_regimes,)
    expert_rmses     : per-expert rolling RMSE            (n_regimes,)
    shared_forecast  : SharedExpert one-step forecast     (scalar)
    top_k            : number of experts to activate      (§9.2: "top k experts")
    c                : scale constant for inverse-RMSE quality weight
    """
    n = len(regime_probs)
    top_k = min(top_k, n)

    # ── 1. Select top-k experts by CJM regime probability ────────────────────
    top_k_idx = np.argsort(regime_probs)[-top_k:]          # indices of top-k

    p_k  = regime_probs[top_k_idx]
    fc_k = expert_forecasts[top_k_idx]
    rm_k = expert_rmses[top_k_idx]

    # Re-normalise probabilities over the top-k subset
    p_k_sum = p_k.sum()
    p_k_norm = p_k / (p_k_sum + 1e-8)

    # ── 2. Quality scalar q = Σ(c/rmse_i · p_i) / Σ(c/rmse_i) ──────────────
    inv_rmse_k = c / (rm_k + 1e-8)
    q = float(np.dot(inv_rmse_k, p_k_norm) / (inv_rmse_k.sum() + 1e-8))
    q = np.clip(q, 0.0, 1.0)

    # ── 3. Regime-weighted forecast over top-k, blended with shared expert ───
    regime_weighted = float(np.dot(p_k_norm, fc_k))
    return q * regime_weighted + (1.0 - q) * shared_forecast


# ──────────────────────────────────────────────────────────────────────────────
# Top-level XAI model
# ──────────────────────────────────────────────────────────────────────────────

class XAI(BaseEstimator, RegressorMixin):
    """
    Regime-aware XAI forecaster: CJM → MoE[ARIMA+LSSVM] → combined forecast.

    Parameters
    ----------
    n_regimes : int
        Number of market regimes for the CJM.
    jump_penalty : float
        CJM smoothness penalty (training phase).  Recommend ~600 for CJM.
    online_jump_penalty : float
        CJM penalty used during online inference. Lower → more responsive.
    lookback : int
        Lag window for LSSVM residual features.
    error_window : int
        Rolling window (days) for expert RMSE tracking inside MoE.
    vol_windows : tuple[int]
        Rolling windows used to compute vol features for CJM.
    clip_std : float
        σ-clipping applied to CJM features before standardisation.
    top_k : int
        Number of experts activated per inference step (§9.2).
        Must be ≤ n_regimes.  Default 2.
    c : float
        Scale constant in the quality weight  q = c / rmse_i.
        Higher c amplifies the penalty on high-error experts.  Default 1.0.
    """

    def __init__(
            self,
            n_regimes: int = 3,
            jump_penalty: float = 600.0,
            online_jump_penalty: float = 60.0,
            lookback: int = 10,
            error_window: int = 21,
            vol_windows: tuple = (5, 21, 63),
            clip_std: float = 3.0,
            top_k: int = 1,
            c: float = 1.0,
    ):
        super().__init__()
        self.n_regimes = n_regimes
        self.jump_penalty = jump_penalty
        self.online_jump_penalty = online_jump_penalty
        self.lookback = lookback
        self.error_window = error_window
        self.vol_windows = vol_windows
        self.clip_std = clip_std
        self.top_k = top_k
        self.c = c

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(self,X, prices: pd.Series) -> "XAI":
        """
        Full training pipeline (§7.1):

        prices : pd.Series  – raw closing price series (training split only)
        """
        prices = prices.ffill()

        # ── 1. CJM feature engineering & preprocessing ────────────────────────
        feats_raw = _make_cjm_features(prices, self.vol_windows)
        aligned_prices = prices.loc[feats_raw.index]   # drop warm-up rows

        self.clipper_ = DataClipper(std=self.clip_std)
        self.scaler_ = DataScaler()
        feats_proc = self.scaler_.fit_transform(self.clipper_.fit_transform(feats_raw))

        # ── 2. Fit CJM → regime labels ────────────────────────────────────────
        self.cjm_ = JumpModel(
            n_components=self.n_regimes,
            jump_penalty=self.jump_penalty,
            cont=True,
        )
        self.cjm_.fit(feats_proc)

        # Hard dominant regime per day (for splitting training data)
        regime_labels: np.ndarray = self.cjm_.labels_    # shape (T,)
        regime_probas: np.ndarray = self.cjm_.proba_     # shape (T, n_regimes)

        price_arr = aligned_prices.values

        # ── 3. Train one expert per regime  ───────────────────────────────────
        self.experts_: list[_Expert] = []
        for r in range(self.n_regimes):
            mask = regime_labels == r
            regime_prices = price_arr[mask]
            expert = _Expert(self.lookback, self.error_window)
            expert.fit(regime_prices)
            self.experts_.append(expert)

        # ── 4. Train shared expert on full data (fallback during transitions) ─
        self.shared_expert_ = _Expert(self.lookback, self.error_window)
        self.shared_expert_.fit(price_arr)

        # ── 5. Prepare CJM for online inference ───────────────────────────────
        # Lower jump_penalty for faster online regime detection
        self.cjm_.set_params(jump_penalty=self.online_jump_penalty)

        # Store the processed feature history so predict_proba_online can
        # condition on everything seen so far.
        self._feat_history: pd.DataFrame = feats_proc
        self._price_history: pd.Series = aligned_prices

        self.fitted_ = True
        return self

    def predict(self, X) -> dict:
        """
        Produce a one-step-ahead forecast.

        Parameters
        ----------
        new_price : float or None
        If provided, the model first ingests this observation (online update),
        then forecasts the *next* step.
        Pass None to forecast from the current state without updating.

        Returns
            forecast      – combined MoE price forecast
        """
        check_is_fitted(self, "fitted_")

        # ── CJM online regime probabilities ──────────────────────────────────
        # predict_proba_online over the full seen history — causal by design.
        online_proba: pd.DataFrame = self.cjm_.predict_proba_online(self._feat_history)
        current_proba: np.ndarray = online_proba.iloc[-1].values   # (n_regimes,)

        threshold = np.partition(current_proba.flatten(), -self.top_k)[-self.top_k]
        result = np.where(current_proba >= threshold,current_proba, 0)
        current_proba = result

        # ── Expert forecasts ──────────────────────────────────────────────────
        expert_fcs = np.zeros(self.n_regimes)
        expert_rmses = np.zeros(self.n_regimes)
        for i, exp in enumerate(self.experts_):
            if current_proba[i] == 0:
                continue # Sparse MoE
            fc, rmse = exp.predict()
            expert_fcs[i] = fc
            expert_rmses[i] = rmse

        shared_fc, _ = self.shared_expert_.predict()

        # ── MoE aggregation ───────────────────────────────────────────────────
        forecast = _moe_aggregate(current_proba, expert_fcs, expert_rmses, shared_fc, top_k=self.top_k, c=self.c)

        return [forecast]

    # ── Online update (partial_fit) ───────────────────────────────────────────

    def partial_fit(self, new_price: float) -> "XAI":
        """
        Ingest one new price observation and update all sub-models.

        Intended to be called once per trading day during live inference.
        """
        check_is_fitted(self, "fitted_")
        self._ingest(new_price)
        return self

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        dump(self, path)

    @classmethod
    def load(cls, path: str) -> "XAI":
        return load(path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ingest(self, new_price: float) -> None:
        """
        Update all sub-models with one new price observation.

        1. Append to price history and recompute CJM features.
        2. Update all regime experts + shared expert.
        """
        # Extend price history
        new_idx = (
                self._price_history.index[-1] + pd.tseries.frequencies.to_offset("1B")
        )
        new_row = pd.Series([new_price], index=[new_idx])
        self._price_history = pd.concat([self._price_history, new_row])

        # Recompute features (only the tail matters; rolling windows are short)
        tail_prices = self._price_history.iloc[-(max(self.vol_windows) + 2):]
        new_feats_raw = _make_cjm_features(tail_prices, self.vol_windows)
        if new_feats_raw.empty:
            return

        # Transform with frozen clipper/scaler
        new_feats_proc = self.scaler_.transform(self.clipper_.transform(new_feats_raw))

        # Append the latest row to feature history
        self._feat_history = pd.concat(
            [self._feat_history, new_feats_proc.iloc[[-1]]]
        )

        # Update all experts with the new actual price
        for exp in self.experts_:
            exp.update(new_price)
        self.shared_expert_.update(new_price)