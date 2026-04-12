import numpy as np
from neo_ls_svm import NeoLSSVM
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_array, check_is_fitted


class LSSVM(BaseEstimator, RegressorMixin):
    def __init__(self, lookback_period=10):
        super().__init__()
        self.n = lookback_period

    def _apply_positional_encoding(self, X):
        """
        Positional encoding can improve the performance of lssvms on sequential data.
        However in this study it has been left as is, to recreate the work of Behera et al.
        and highlight improvements due to CJM.

        :param X:
        :return:
        """
        return X

    def _make_windows(self, y: np.ndarray):
        """Slide a window of size n+1 over y → X (n predictors), t (1 target)."""
        windows = np.lib.stride_tricks.sliding_window_view(y, self.n + 1)
        # windows shape: (len(y) - n, n + 1)
        return windows[:, :-1], windows[:, -1]   # X, t

    def fit(self, X, y):
        y = check_array(y, ensure_2d=False)
        X_w, t_w = self._make_windows(y)

        self.model_ = NeoLSSVM()
        X_w = self._apply_positional_encoding(X_w)
        self.model_.fit(X_w, t_w)

        self.fitted_ = True
        return self

    def predict(self, X):
        check_is_fitted(self)
        # X = [[1]] → next-step forecast
        fc = self.model_.predict(n_periods=X[0][0])
        return fc

    def partial_fit(self, X, y: np.ndarray):
        return self