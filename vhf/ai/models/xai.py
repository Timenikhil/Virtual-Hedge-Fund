import numpy as np
import pmdarima as pm
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted
from jumpmodels.jump import JumpModel

from vhf.ai.models.lssvm import LSSVM


class XAI(BaseEstimator, RegressorMixin):
    def __init__(self,n_regimes = 3,jump_penalty = 1.0,lookback_period = 10):
        super().__init__()
        self.n_regimes = n_regimes
        self.jump_penalty = jump_penalty
        self.cjm_ = JumpModel(n_components=self.n_regimes,jump_penalty=self.jump_penalty,cont=True)
        self.experts_ = []

    def fit(self, X, y:np.ndarray):
        y = check_array(y, ensure_2d=False)
        self.cjm_.fit(y)

        

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
