import pandas as pd
from moonshot import Moonshot

class MyMoonshotStrategy(Moonshot):

    CODE = "my-strategy" 
    DB = "usstock-1d"

    def prices_to_signals(self, prices: pd.DataFrame):
        """
        From a DataFrame of prices, return a DataFrame of signals. By convention,
        signals should be 1=long, 0=cash, -1=short.
        """
        # Buy when the close is above the 50-period moving average.
        closes = prices.loc["Close"]
        mavgs = closes.rolling(50).mean()
        signals = closes > mavgs.shift()
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
