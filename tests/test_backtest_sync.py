"""
Unit tests for vhf.quantrocket.backtest_sync.
All HTTP and DB calls are mocked — no QuantRocket or network required.
"""

import unittest
from unittest.mock import MagicMock, call, patch

from vhf.quantrocket.backtest_sync import BacktestSyncError, sync_strategy_backtest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(*return_rows: tuple[str, float]) -> str:
    """Build a minimal houston backtest CSV string."""
    lines = ["Field,Date,my_strategy"]
    for date, ret in return_rows:
        lines.append(f"Return,{date},{ret}")
        lines.append(f"AbsExposure,{date},0.999")  # non-Return row — should be ignored
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class SyncStrategyBacktestTest(unittest.TestCase):

    @patch("vhf.quantrocket.backtest_sync.record_strategy_price_points")
    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_stores_cumulative_price_series(self, mock_post, mock_record):
        """Return series 0%, +10%, -5% should produce cumulative prices 110, 104.5."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text=_csv(
                ("2025-01-02", 0.0),
                ("2025-01-03", 0.10),
                ("2025-01-06", -0.05),
            ),
            raise_for_status=MagicMock(),
        )

        n = sync_strategy_backtest("my_strategy")

        # Leading zero-return rows are dropped, so 2 active rows
        self.assertEqual(n, 2)
        stored = mock_record.call_args[0][1]
        self.assertEqual(len(stored), 2)
        dates = [p[0] for p in stored]
        self.assertEqual(dates, ["2025-01-03", "2025-01-06"])
        self.assertAlmostEqual(stored[0][1], 110.0, places=4)
        self.assertAlmostEqual(stored[1][1], 104.5, places=4)

    @patch("vhf.quantrocket.backtest_sync.record_strategy_price_points")
    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_drops_leading_zero_returns(self, mock_post, mock_record):
        """Warm-up (zero-return) rows at the start are stripped before indexing."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text=_csv(
                ("2025-01-02", 0.0),
                ("2025-01-03", 0.0),
                ("2025-01-06", 0.05),
            ),
            raise_for_status=MagicMock(),
        )

        n = sync_strategy_backtest("my_strategy")

        stored = mock_record.call_args[0][1]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0][0], "2025-01-06")

    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_raises_on_http_error(self, mock_post):
        """HTTP 4xx/5xx from houston raises BacktestSyncError."""
        import requests as req
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=req.HTTPError("500 Server Error")),
        )

        with self.assertRaises(BacktestSyncError):
            sync_strategy_backtest("bad_strategy")

    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_raises_on_empty_return_rows(self, mock_post):
        """CSV with no Return rows raises BacktestSyncError."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text="Field,Date,my_strategy\nAbsExposure,2025-01-02,0.999",
            raise_for_status=MagicMock(),
        )

        with self.assertRaises(BacktestSyncError) as cm:
            sync_strategy_backtest("my_strategy")

        self.assertIn("No Return rows", str(cm.exception))

    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_raises_on_network_error(self, mock_post):
        """Connection error raises BacktestSyncError."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("refused")

        with self.assertRaises(BacktestSyncError):
            sync_strategy_backtest("my_strategy")

    @patch("vhf.quantrocket.backtest_sync.record_strategy_price_points")
    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_passes_date_params_to_houston(self, mock_post, mock_record):
        """start_date and end_date are forwarded as query params."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text=_csv(("2025-03-01", 0.01)),
            raise_for_status=MagicMock(),
        )

        sync_strategy_backtest("my_strategy", start_date="2025-01-01", end_date="2025-12-31")

        call_kwargs = mock_post.call_args[1]
        params = call_kwargs.get("params", mock_post.call_args[0][0] if mock_post.call_args[0] else {})
        # params may be positional or keyword
        params = mock_post.call_args.kwargs.get("params") or mock_post.call_args.args[0] if mock_post.call_args.args else {}
        params = mock_post.call_args[1].get("params", {})
        self.assertEqual(params.get("start_date"), "2025-01-01")
        self.assertEqual(params.get("end_date"), "2025-12-31")

    @patch("vhf.quantrocket.backtest_sync.record_strategy_price_points")
    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_price_series_sorted_by_date(self, mock_post, mock_record):
        """Output price series is sorted ascending by date regardless of CSV order."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text=_csv(
                ("2025-01-06", 0.02),
                ("2025-01-03", 0.01),  # out of order
            ),
            raise_for_status=MagicMock(),
        )

        sync_strategy_backtest("my_strategy")

        stored = mock_record.call_args[0][1]
        dates = [p[0] for p in stored]
        self.assertEqual(dates, sorted(dates))

    @patch("vhf.quantrocket.backtest_sync.record_strategy_price_points")
    @patch("vhf.quantrocket.backtest_sync.requests.post")
    def test_returns_point_count(self, mock_post, mock_record):
        """Return value equals the number of price points stored."""
        mock_post.return_value = MagicMock(
            status_code=200,
            text=_csv(
                ("2025-01-02", 0.0),
                ("2025-01-03", 0.01),
                ("2025-01-06", 0.02),
                ("2025-01-07", -0.01),
            ),
            raise_for_status=MagicMock(),
        )

        n = sync_strategy_backtest("my_strategy")

        self.assertEqual(n, mock_record.call_args[0][1].__len__())
        self.assertEqual(n, 3)  # first zero row dropped


if __name__ == "__main__":
    unittest.main()
