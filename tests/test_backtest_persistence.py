"""
Unit tests for backtest result persistence DB operations.
All DB calls are mocked — no real database required.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException


def _make_mock_conn(mock_conn):
    """Return the MagicMock that will be `cursor` inside `with closing(...) as cursor`."""
    return mock_conn.client.cursor.return_value


def _fake_result_json(portfolio_id=1, method="equal_weight"):
    """Minimal BacktestResult JSON blob for testing."""
    return json.dumps({
        "portfolio_id": portfolio_id,
        "method": method,
        "start_date": "2025-01-02",
        "end_date": "2025-06-30",
        "n_trading_days": 125,
        "n_rebalances": 6,
        "initial_value": 100.0,
        "final_value": 112.34,
        "total_return_pct": 12.34,
        "annualised_return_pct": 24.68,
        "sharpe_ratio": 1.42,
        "max_drawdown_pct": -4.21,
        "strategy_legs": [],
        "daily_values": [],
        "rebalance_history": [],
        "ai_call_count": None,
        "ai_fallback_count": None,
        "weight_stability": None,
    })


class SaveBacktestResultTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_save_returns_row_id(self, mock_conn):
        from vhf.db.operations import save_backtest_result

        cursor = _make_mock_conn(mock_conn)
        cursor.lastrowid = 42

        result = MagicMock()
        result.portfolio_id = 1
        result.method = "equal_weight"
        result.start_date = "2025-01-02"
        result.end_date = "2025-06-30"
        result.initial_value = 100.0
        result.model_dump_json.return_value = _fake_result_json()

        row_id = save_backtest_result(result, rebalance_frequency_days=21)

        self.assertEqual(row_id, 42)
        cursor.execute.assert_called_once()
        mock_conn.client.commit.assert_called_once()

    @patch("vhf.db.operations.connection")
    def test_save_inserts_correct_fields(self, mock_conn):
        from vhf.db.operations import save_backtest_result

        cursor = _make_mock_conn(mock_conn)
        cursor.lastrowid = 1

        result = MagicMock()
        result.portfolio_id = 7
        result.method = "ai_weighted"
        result.start_date = "2024-01-02"
        result.end_date = "2024-12-31"
        result.initial_value = 1000.0
        result.model_dump_json.return_value = _fake_result_json(7, "ai_weighted")

        save_backtest_result(result, rebalance_frequency_days=10)

        call_args = cursor.execute.call_args
        params = call_args[0][1]  # (sql, params)
        self.assertEqual(params[0], 7)        # PID
        self.assertEqual(params[1], "ai_weighted")  # METHOD
        self.assertEqual(params[4], 10)       # REBALANCE_FREQUENCY_DAYS
        self.assertEqual(params[5], 1000.0)   # INITIAL_VALUE


class ListBacktestResultsTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_returns_empty_list_when_no_rows(self, mock_conn):
        from vhf.db.operations import list_backtest_results

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchall.return_value = []

        result = list_backtest_results(portfolio_id=1)

        self.assertEqual(result, [])

    @patch("vhf.db.operations.connection")
    def test_returns_summary_dicts(self, mock_conn):
        from vhf.db.operations import list_backtest_results

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchall.return_value = [
            (1, 5, "equal_weight", "2025-01-02", "2025-06-30", 21, 100.0,
             "2025-06-30T12:00:00+00:00", 12.34, 24.68, 1.42, -4.21, 125, 6, 112.34),
        ]

        rows = list_backtest_results(portfolio_id=5)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["portfolio_id"], 5)
        self.assertEqual(row["method"], "equal_weight")
        self.assertAlmostEqual(row["total_return_pct"], 12.34)
        self.assertAlmostEqual(row["sharpe_ratio"], 1.42)
        self.assertEqual(row["n_rebalances"], 6)

    @patch("vhf.db.operations.connection")
    def test_handles_null_metrics_gracefully(self, mock_conn):
        """Rows with NULL metrics (e.g. sharpe when <2 returns) should use None."""
        from vhf.db.operations import list_backtest_results

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchall.return_value = [
            (2, 1, "score_weighted", "2025-01-02", "2025-01-04", 21, 100.0,
             "2025-01-04T00:00:00+00:00", 0.5, None, None, -0.1, 2, 0, 100.5),
        ]

        rows = list_backtest_results(portfolio_id=1)

        self.assertIsNone(rows[0]["sharpe_ratio"])
        self.assertIsNone(rows[0]["annualised_return_pct"])

    @patch("vhf.db.operations.connection")
    def test_queries_correct_portfolio_id(self, mock_conn):
        from vhf.db.operations import list_backtest_results

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchall.return_value = []

        list_backtest_results(portfolio_id=99)

        call_args = cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 99)


class GetBacktestResultTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_returns_parsed_json(self, mock_conn):
        from vhf.db.operations import get_backtest_result

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchone.return_value = (_fake_result_json(3, "manual"),)

        result = get_backtest_result(run_id=10)

        self.assertEqual(result["portfolio_id"], 3)
        self.assertEqual(result["method"], "manual")
        self.assertAlmostEqual(result["total_return_pct"], 12.34)

    @patch("vhf.db.operations.connection")
    def test_raises_404_when_not_found(self, mock_conn):
        from vhf.db.operations import get_backtest_result

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchone.return_value = None

        with self.assertRaises(HTTPException) as cm:
            get_backtest_result(run_id=999)

        self.assertEqual(cm.exception.status_code, 404)

    @patch("vhf.db.operations.connection")
    def test_queries_by_run_id(self, mock_conn):
        from vhf.db.operations import get_backtest_result

        cursor = _make_mock_conn(mock_conn)
        cursor.fetchone.return_value = (_fake_result_json(),)

        get_backtest_result(run_id=55)

        call_args = cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 55)


if __name__ == "__main__":
    unittest.main()
