import pandas as pd

from vhf.ai.train import train_model
from vhf.db.operations import get_all_sids, get_prices, store_prices, store_strategy
from vhf.db.ranking import insert_error, insert_corr


def register_strategy(sid,name,description,category,prices:pd.Series,algos=[],computeCorr=True):
    """

    :param sid:
    :param name:
    :param description:
    :param category:
    :param prices:
    :param algos:
    :param computeCorr:
    :return:

    1. stores the details in the db
    2. trains the given algos from the list, and stores the errors and the model parameters
    3. computes Corr with all previous strategies if ComputeCorr is set to True

    The parameters are allowed to be null, as training so many models and finding correlations
    can be time consuming
    """

    store_strategy(sid,name,description,category,prices[-5:])
    store_prices(sid,prices)

    for algo in algos:
        error = train_model(algo,prices.ffill(),sid)
        insert_error(sid,algo,error)

    if computeCorr:
        sids = get_all_sids()
        for osid in sids:
            if osid == sid:
                continue
            oprice = get_prices(osid)
            insert_corr(sid,osid,prices.corr(oprice))