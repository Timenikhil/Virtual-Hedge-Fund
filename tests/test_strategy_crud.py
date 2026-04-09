"""
Unit tests for strategy CRUD DB operations and admin API endpoints.
All DB calls are mocked — no real database required.
"""

import unittest
from unittest.mock import MagicMock, call, patch

from fastapi import HTTPException

from tests.fixtures import (
    STRATEGIES,
    PRICE_POINTS,
    strategy_factory,
    price_points_factory,
    allocation_context_factory,
)
from vhf.models.strategy import Strategy


# ---------------------------------------------------------------------------
# Helper: build a patched connection where closing() returns mock_cursor
# The actual code uses `with closing(connection.client.cursor()) as cursor:`.
# contextlib.closing.__enter__ returns self.thing directly — so the cursor
# in the with-block is connection.client.cursor(), i.e. cursor.return_value.
# ---------------------------------------------------------------------------

def _make_mock_conn(mock_conn):
    """Return the MagicMock that will be `cursor` inside the with-block."""
    mock_cursor = mock_conn.client.cursor.return_value
    return mock_cursor


# ---------------------------------------------------------------------------
# DB operations: upsert_strategy
# ---------------------------------------------------------------------------

class UpsertStrategyTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_upsert_new_strategy_returns_strategy(self, mock_conn):
        from vhf.db.operations import upsert_strategy

        result = upsert_strategy(
            strategy_id="test_strat",
            name="Test",
            description="desc",
            category="equity",
        )

        self.assertIsInstance(result, Strategy)
        self.assertEqual(result.strategy_id, "test_strat")
        self.assertEqual(result.name, "Test")
        self.assertEqual(result.category, "equity")

    @patch("vhf.db.operations.connection")
    def test_upsert_executes_insert_on_conflict(self, mock_conn):
        from vhf.db.operations import upsert_strategy

        mock_cursor = _make_mock_conn(mock_conn)

        upsert_strategy(
            strategy_id="s1",
            name="Name",
            description="desc",
            category="equity",
        )

        executed_sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("ON CONFLICT", executed_sql)
        self.assertIn("DO UPDATE", executed_sql)

    @patch("vhf.db.operations.connection")
    def test_upsert_commits_and_syncs(self, mock_conn):
        from vhf.db.operations import upsert_strategy

        upsert_strategy(strategy_id="s1", name="N", description="d", category="equity")

        mock_conn.client.commit.assert_called_once()


# ---------------------------------------------------------------------------
# DB operations: bulk_upsert_strategies
# ---------------------------------------------------------------------------

class BulkUpsertStrategiesTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_bulk_upsert_returns_all_strategies(self, mock_conn):
        from vhf.db.operations import bulk_upsert_strategies

        results = bulk_upsert_strategies(STRATEGIES[:3])

        self.assertEqual(len(results), 3)
        self.assertIsInstance(results[0], Strategy)
        self.assertEqual(results[0].strategy_id, STRATEGIES[0]["strategy_id"])

    @patch("vhf.db.operations.connection")
    def test_bulk_upsert_uses_executemany(self, mock_conn):
        from vhf.db.operations import bulk_upsert_strategies

        mock_cursor = _make_mock_conn(mock_conn)

        bulk_upsert_strategies(STRATEGIES[:5])

        mock_cursor.executemany.assert_called_once()
        # Payload should have 5 rows.
        payload = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(payload), 5)

    @patch("vhf.db.operations.connection")
    def test_bulk_upsert_empty_list_returns_empty(self, mock_conn):
        from vhf.db.operations import bulk_upsert_strategies

        results = bulk_upsert_strategies([])
        self.assertEqual(results, [])
        mock_conn.client.cursor.assert_not_called()

    def test_bulk_upsert_raises_on_empty_strategy_id(self):
        from vhf.db.operations import bulk_upsert_strategies

        with self.assertRaises(HTTPException) as ctx:
            bulk_upsert_strategies([{"strategy_id": "", "name": "N", "description": "", "category": "eq"}])
        self.assertEqual(ctx.exception.status_code, 400)


# ---------------------------------------------------------------------------
# DB operations: delete_strategy
# ---------------------------------------------------------------------------

class DeleteStrategyTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_delete_existing_strategy(self, mock_conn):
        from vhf.db.operations import delete_strategy

        mock_cursor = _make_mock_conn(mock_conn)
        mock_cursor.fetchone.return_value = (1,)  # strategy exists

        delete_strategy("test_strat")

        mock_conn.client.commit.assert_called_once()

    @patch("vhf.db.operations.connection")
    def test_delete_missing_strategy_raises_404(self, mock_conn):
        from vhf.db.operations import delete_strategy

        mock_cursor = _make_mock_conn(mock_conn)
        mock_cursor.fetchone.return_value = None  # strategy does not exist

        with self.assertRaises(HTTPException) as ctx:
            delete_strategy("nonexistent")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("vhf.db.operations.connection")
    def test_delete_removes_price_history_before_strategy(self, mock_conn):
        from vhf.db.operations import delete_strategy

        mock_cursor = _make_mock_conn(mock_conn)
        mock_cursor.fetchone.return_value = (1,)

        delete_strategy("s1")

        calls = [c[0][0].strip() for c in mock_cursor.execute.call_args_list]
        # Find the DELETE calls (not the SELECT 1 check)
        delete_calls = [sql for sql in calls if sql.startswith("DELETE")]
        self.assertEqual(len(delete_calls), 2)
        # Price history must be deleted before the strategy row.
        self.assertIn("strategy_price_history", delete_calls[0])
        self.assertIn("strategies", delete_calls[1])


# ---------------------------------------------------------------------------
# DB operations: record_strategy_price_points
# ---------------------------------------------------------------------------

class RecordStrategyPricePointsTest(unittest.TestCase):
    @patch("vhf.db.operations.connection")
    def test_records_valid_points(self, mock_conn):
        from vhf.db.operations import record_strategy_price_points

        mock_cursor = _make_mock_conn(mock_conn)

        points = price_points_factory("s1", n=5)
        record_strategy_price_points("s1", points)

        mock_cursor.executemany.assert_called_once()
        payload = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(payload), 5)

    @patch("vhf.db.operations.connection")
    def test_skips_non_finite_prices(self, mock_conn):
        from vhf.db.operations import record_strategy_price_points

        mock_cursor = _make_mock_conn(mock_conn)

        points = [
            ("2025-01-02", 1000.0),
            ("2025-01-03", float("inf")),   # invalid
            ("2025-01-06", float("nan")),   # invalid
            ("2025-01-07", 1020.0),
        ]
        record_strategy_price_points("s1", points)

        payload = mock_cursor.executemany.call_args[0][1]
        self.assertEqual(len(payload), 2)  # only the two valid points

    @patch("vhf.db.operations.connection")
    def test_no_db_call_when_all_points_invalid(self, mock_conn):
        from vhf.db.operations import record_strategy_price_points

        points = [("2025-01-02", float("nan")), ("2025-01-03", float("inf"))]
        record_strategy_price_points("s1", points)

        mock_conn.client.cursor.assert_not_called()


# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------

class FixtureIntegrityTest(unittest.TestCase):
    def test_all_strategies_have_required_fields(self):
        for s in STRATEGIES:
            for field in ("strategy_id", "name", "description", "category"):
                self.assertIn(field, s, f"Strategy {s} missing field {field!r}")
                self.assertTrue(s[field], f"Strategy {s} has empty {field!r}")

    def test_no_duplicate_strategy_ids(self):
        ids = [s["strategy_id"] for s in STRATEGIES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_price_points_are_chronological(self):
        for sid, points in PRICE_POINTS.items():
            dates = [p[0] for p in points]
            self.assertEqual(dates, sorted(dates), f"{sid} price points not in order")

    def test_price_points_are_positive(self):
        for sid, points in PRICE_POINTS.items():
            for ts, price in points:
                self.assertGreater(price, 0, f"{sid}@{ts} has non-positive price")

    def test_strategy_factory_defaults(self):
        s = strategy_factory()
        self.assertEqual(s["strategy_id"], "test_strat")

    def test_strategy_factory_overrides(self):
        s = strategy_factory(strategy_id="custom", category="macro")
        self.assertEqual(s["strategy_id"], "custom")
        self.assertEqual(s["category"], "macro")

    def test_price_points_factory_length(self):
        pts = price_points_factory("s1", n=10)
        self.assertEqual(len(pts), 10)

    def test_price_points_factory_ascending(self):
        pts = price_points_factory("s1", n=5, start=100.0, step=5.0)
        prices = [p[1] for p in pts]
        self.assertEqual(prices, sorted(prices))

    def test_allocation_context_factory_structure(self):
        ctx = allocation_context_factory(["s1", "s2"])
        self.assertEqual(ctx["strategies"], ["s1", "s2"])
        self.assertEqual(len(ctx["strategy_data"]), 2)
        self.assertEqual(len(ctx["current_weights"]), 2)


# ---------------------------------------------------------------------------
# Seed script: dry-run mode (no DB required)
# ---------------------------------------------------------------------------

class SeedScriptDryRunTest(unittest.TestCase):
    def test_seed_strategies_dry_run_produces_no_db_calls(self):
        """_seed_strategies(dry_run=True) must not touch the DB layer."""
        import scripts.seed as seed_module

        with patch("vhf.db.operations.upsert_strategy") as mock_upsert, \
             patch("vhf.db.operations.record_strategy_price_points") as mock_prices:
            seed_module._seed_strategies(dry_run=True)
            mock_upsert.assert_not_called()
            mock_prices.assert_not_called()

    def test_seed_generates_correct_number_of_price_points(self):
        """Each strategy should get exactly 252 trading-day price points."""
        import scripts.seed as seed_module

        strat = seed_module.STRATEGIES[0]
        points = seed_module._generate_prices(
            annual_drift=strat["annual_drift"],
            annual_vol=strat["annual_vol"],
        )
        self.assertEqual(len(points), 252)

    def test_seed_prices_are_positive(self):
        import scripts.seed as seed_module

        for strat in seed_module.STRATEGIES:
            points = seed_module._generate_prices(
                annual_drift=strat["annual_drift"],
                annual_vol=strat["annual_vol"],
                seed=42,
            )
            for ts, price in points:
                self.assertGreater(price, 0, f"{strat['strategy_id']}@{ts} price <= 0")

    def test_seed_prices_are_deterministic(self):
        import scripts.seed as seed_module

        pts1 = seed_module._generate_prices(0.10, 0.15, seed=7)
        pts2 = seed_module._generate_prices(0.10, 0.15, seed=7)
        self.assertEqual(pts1, pts2)

    def test_seed_different_seeds_produce_different_prices(self):
        import scripts.seed as seed_module

        pts1 = seed_module._generate_prices(0.10, 0.15, seed=1)
        pts2 = seed_module._generate_prices(0.10, 0.15, seed=2)
        self.assertNotEqual(pts1, pts2)

    def test_all_seed_strategy_ids_are_unique(self):
        import scripts.seed as seed_module

        ids = [s["strategy_id"] for s in seed_module.STRATEGIES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_portfolio_strategies_exist_in_seed(self):
        import scripts.seed as seed_module

        strat_ids = {s["strategy_id"] for s in seed_module.STRATEGIES}
        for portfolio in seed_module.PORTFOLIOS:
            for sid in portfolio["strategies"]:
                self.assertIn(sid, strat_ids, f"Portfolio {portfolio['portfolio_name']} references unknown strategy {sid}")


if __name__ == "__main__":
    unittest.main()
