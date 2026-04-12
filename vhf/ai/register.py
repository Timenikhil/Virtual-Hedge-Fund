def register_strategy(sid,name,description,category,prices,algos=[],computeCorr=True):
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
    pass