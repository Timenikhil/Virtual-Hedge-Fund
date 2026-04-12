import numpy as np
import pmdarima as pm
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted

from vhf.ai.models.lssvm import LSSVM


class EXPERT(BaseEstimator, RegressorMixin):
    def __init__(self,split = 0.6,lookback_period = 10):
        super().__init__()
        self.split = split
        self.n = lookback_period

    def fit(self, X, y:np.ndarray):
        y = check_array(y, ensure_2d=False)
        arima_train = self.split * len(y)
        prices = y
        train, test = prices[:arima_train], prices[arima_train:]
        self.arima_ = pm.auto_arima(train)

        predictions = []
        for obs in test:
            pred = self.arima_.predict([[1]])[0] # next step forecasting
            predictions.append(pred)
            self.arima_.update(obs)

        predictions = np.array(predictions)
        residuals = y - predictions
        self.lssvm_ = LSSVM(lookback_period=self.n)
        self.lssvm_.fit(None,residuals)
        self.fitted_ = True
        return self

    def predict(self, X):
        check_is_fitted(self)
        ar = self.arima_.predict(n_periods=X[0][0]) # next step forecasting, set X = [[1]]
        ls = self.lssvm_.predict(X)
        return ar + ls
    def partial_fit(self, X, y:np.ndarray):
        y = check_array(y, ensure_2d=False)
        self.arima_.update(y[0])
        self.lssvm_.partial_fit(X,y)
        return self
