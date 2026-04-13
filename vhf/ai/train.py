import os

import numpy as np
from joblib import dump, load
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.dummy import DummyRegressor
from sklearn.metrics import root_mean_squared_error

from vhf.ai.models.arima import ARIMA
from vhf.ai.models.lssvm import LSSVM

"""
The models are trained and their Root Mean Squared Error is propagated
back. The RMSE is calculated only on held-out data and not on in sample data to avoid
overfitting creating artificially low scores even via leakage.

By default, a 7:3 split is used to find errors as described in the report.
The value can be modified via the env variable, but it should be remembered that
having different data splits midway may make past results less reliable/comparable.

The necessary files are stored via model_dumps, and restored later via joblib.
The strategies are made to follow scikit_learn api for interoperability.

"""

def train_model(algo,prices:np.ndarray,sid) -> float:
    model : RegressorMixin = DummyRegressor()
    match algo:
        case "ARIMA":
            model =  ARIMA()
        case "LSSVM":
            model =  LSSVM()
        case "EXPERT":
            model = EXPERT()
        case "XAI":
            model =  XAI()
        case _:
            return -1


    train_ratio = os.getenv("TRAIN_SPLIT",0.7)
    train_len = int(len(prices) * train_ratio)
    train, test = prices[:train_len], prices[train_len:]
    model.fit(train)
    # Walk-Forward Validation on test set
    predictions = []
    for obs in test:
        pred = model.predict([[1]])[0] # next step forecasting
        predictions.append(pred)
        model.partial_fit(None,[obs])

    predictions = np.array(predictions)
    error = root_mean_squared_error(test, predictions)

    model.fit(prices)
    dump(model, f'./models/weights/{algo}-{sid}.joblib')

    return error


