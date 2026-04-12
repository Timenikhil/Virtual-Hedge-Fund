import numpy as np
import pmdarima as pm
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted

class ARIMA(BaseEstimator, RegressorMixin):
    def __init__(self):
        super().__init__()

    def fit(self, X, y):
        y = check_array(y, ensure_2d=False)
        self.model_ = pm.auto_arima(y)
        self.fitted_ = True
        return self

    def predict(self, X):
        check_is_fitted(self)
        fc = self.model_.predict(n_periods=X[0][0]) # next step forecasting, set X = [[1]]
        return fc
    def partial_fit(self, X, y:np.ndarray):
        y = check_array(y, ensure_2d=False)
        self.model_.update(y[0])
        return self

