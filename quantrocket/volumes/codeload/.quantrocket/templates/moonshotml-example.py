import pandas as pd
from moonshot import MoonshotML

class MyMoonshotMLStrategy(MoonshotML):

    CODE = "my-ml-strategy" 
    DB = "usstock-1d"
    
    def prices_to_features(self, prices: pd.DataFrame):
        """
        From a DataFrame of prices, return a tuple of features and targets to be
        provided to the machine learning model.

        The returned features can be a list or dict of DataFrames, where each
        DataFrame is a feature and should have the same shape, with a Date or
        (Date, Time) index and sids as columns. (Moonshot will convert the
        DataFrames to the format expected by the machine learning model).

        Alternatively, a list or dict of Series can be provided, which is
        suitable if using multiple securities to make predictions for a
        single security (for example, an index).

        The returned targets should be a DataFrame or Series with an index
        matching the index of the features DataFrames or Series. Targets are
        used in training and are ignored for prediction. (Model training is
        not handled by the MoonshotML class.) Alternatively return None if
        using an already trained model.
        """
        # Predict next-day returns based on 1-day and 2-day returns:
        closes = prices.loc["Close"]
        features = {}
        features["returns_1d"]= closes.pct_change()
        features["returns_2d"] = (closes - closes.shift(2)) / closes.shift(2)
        targets = closes.pct_change().shift(-1)
        return features, targets

    def predictions_to_signals(self, predictions: pd.DataFrame, prices: pd.DataFrame):
        """
        From a DataFrame of predictions produced by a machine learning model,
        return a DataFrame of signals. By convention, signals should be
        1=long, 0=cash, -1=short.

        The index of predictions will match the index of the features
        DataFrames or Series returned in prices_to_features.
        """
        # Buy when prediction (a DataFrame) is above zero.
        signals = predictions > 0
        return signals.astype(int)


    def signals_to_target_weights(self, signals: pd.DataFrame, prices: pd.DataFrame):
        """
        From a DataFrame of signals, return a DataFrame of target weights.

        Whereas signals indicate the direction of the trades, weights
        indicate both the direction and size. For example, -0.5 means a short
        position equal to 50% of the equity allocated to the strategy.
        """
        # Divide capital equally among signals
        daily_signal_counts = signals.abs().sum(axis=1)
        weights = signals.div(daily_signal_counts, axis=0).fillna(0)
        return weights

    def target_weights_to_positions(self, weights: pd.DataFrame, prices: pd.DataFrame):
        """
        From a DataFrame of target weights, return a DataFrame of simulated
        positions. This method only runs in backtests.
        """
        # Enter in the period after the signal
        positions = weights.shift()
        return positions

    def positions_to_gross_returns(self, positions: pd.DataFrame, prices: pd.DataFrame):
        """
        From a DataFrame of positions, return a DataFrame of returns before
        commissions and slippage. This method only runs in backtests.
        """
        closes = prices.loc["Close"]
        gross_returns = closes.pct_change() * positions.shift()
        return gross_returns

    def order_stubs_to_orders(self, orders: pd.DataFrame, prices: pd.DataFrame):
        """
        From a DataFrame of order stubs, creates a DataFrame of fully
        specified orders. This method only runs in live trading.

        The orders DataFrame provided to this method resembles the following:

              Sid  Account Action     OrderRef  TotalQuantity
        0   FI123   U12345   SELL  my-strategy            100
        1   FI123   U55555   SELL  my-strategy             50
        2   FI234   U12345    BUY  my-strategy            100
        3   FI234   U55555    BUY  my-strategy             50
        4   FI345   U12345    BUY  my-strategy            200
        5   FI345   U55555    BUY  my-strategy            100

        At minimum, specify an OrderType and Tif. Some brokers also
        require an Exchange.
        """
        # Send SMART-routed market orders
        orders["Exchange"] = "SMART"
        orders["OrderType"] = "MKT"
        orders["Tif"] = "DAY"
        return orders
