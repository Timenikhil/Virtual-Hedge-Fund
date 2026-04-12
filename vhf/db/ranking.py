from contextlib import closing
from typing import List

from fastapi import HTTPException

from vhf.db import connection

def getTop(sids,algo,k) -> List[str]:
    """
    Retrieves Top K Strategy from given sids

    :return:
    """

    placeholders = ', '.join(['?'] * len(sids))
    algo = algo.upper()

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
        f"""
            SELECT SID
            FROM errors
            WHERE SID IN ({placeholders})
            ORDER BY {algo} ASC NULLS LAST
            LIMIT ?
        """,
            (*sids,k)
        )
        record = cursor.fetchall()
        if not record:
            raise HTTPException(status_code=404, detail="Provided strategies not found")
    return [row[0] for row in record]

def getBottom(sids,algo,k) -> List[str]:
    """
    Retrieves Bottom K Strategy from given sids
    - useful when the strategies aren't good enough on their own,
    but may show significant improvement when combined
    :return:
    """

    placeholders = ', '.join(['?'] * len(sids))
    algo = algo.upper()

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            f"""
                SELECT SID
                FROM errors
                WHERE SID IN ({placeholders})
                ORDER BY {algo} DESC NULLS LAST
                LIMIT ?
            """,
            (*sids,k)
        )
        record = cursor.fetchall()
        if not record:
            raise HTTPException(status_code=404, detail="Provided strategies not found")
    return [row[0] for row in record]

def getMax(sids,algo,k) -> List[str]:
    """
    Retrieves Strategies with max error = K
    - Note this is algorithm sensitive, only use if you know what you are doing
    """

    placeholders = ', '.join(['?'] * len(sids))
    algo = algo.upper()

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            f"""
                    SELECT SID
                    FROM errors
                    WHERE SID IN ({placeholders})
                    AND {algo} <= ?
                """,
            (*sids,k)
        )
        record = cursor.fetchall()
        if not record:
            raise HTTPException(status_code=404, detail="No matching strategies found")
    return [row[0] for row in record]

# This can be extended to have getTopCorr, getBottomCorr similar to the above errors
def getCorr(sids,k) -> List[str]:
    """
    Retrieves Pairwise Corr < K Strategy from given sids

    :return:
    """

    placeholders = ', '.join(['?'] * len(sids))

    connection.connect()
    connection.client.sync()
    with closing(connection.client.cursor()) as cursor:
        cursor.execute(
            f"""
                SELECT SID1,SID2
                FROM corr
                WHERE SID1 IN ({placeholders})
                AND SID2 IN ({placeholders})
                AND corr <= ?
            """,
            (*sids,*sids,k)
        )
        record = cursor.fetchall()
        if not record:
            raise HTTPException(status_code=404, detail="No suitable strategies not found")
    return list(set([row[0] for row in record] + [row[1] for row in record]))


# register_strategy
#
def insert_error(algo,value):
    pass

def insert_corr(sid1,sid2,value):
    value = abs(value)
    pass