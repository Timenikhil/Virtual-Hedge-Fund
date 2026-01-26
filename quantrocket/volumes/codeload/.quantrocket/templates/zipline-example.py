import pandas as pd
import zipline.api as algo
from zipline.pipeline import Pipeline
from zipline.pipeline.data import USEquityPricing
from zipline.pipeline.factors import AverageDollarVolume

class Context(algo.Context):
    """
    Optional subclass of `algo.Context` to improve autocomplate of 
    `context` variables.
    
    In this class, initialize any custom variables you want to add 
    to the `context` object, and specify type hints for the variables, 
    using the form:
    
        <variable_name>: <type>
    
    This class won't be executed in backtests and isn't required, 
    but it will facilitate autocomplete of your context variables.
    """
    # replace these with your own context variable names
    output: pd.DataFrame
    security_list: pd.Index

def initialize(context: Context):
    """
    Called once at the start of a backtest, and once per day at
    the start of live trading. In live trading, the stored context
    will be loaded *after* this function is called.
    """
    # Rebalance every day, 1 hour after market open.
    algo.schedule_function(
        rebalance,
        algo.date_rules.every_day(),
        algo.time_rules.market_open(hours=1),
    )

    # Create a pipeline to select stocks each day.
    algo.attach_pipeline(make_pipeline(), 'pipeline')

def make_pipeline():
    """
    Create a pipeline to select stocks each day.
    """

    # Use a dollar volume filter to select liquid stocks
    liquid_stocks = AverageDollarVolume(
        window_length=30).percentile_between(60, 100)

    # Factor of yesterday's close price.
    yesterday_close = USEquityPricing.close.latest

    pipe = Pipeline(
        columns={
            'close': yesterday_close,
        },
        screen=liquid_stocks
    )
    return pipe

def before_trading_start(context: Context, data: algo.BarData):
    """
    Called every day before market open.
    """
    context.output = algo.pipeline_output('pipeline')

    # These are the securities that we are interested in trading each day.
    context.security_list = context.output.index

def rebalance(context: Context, data: algo.BarData):
    """
    Execute orders according to our schedule_function() timing.
    """
    pass

def handle_data(context: Context, data: algo.BarData):
    """
    Called every minute.
    """
    pass