import unittest
from unittest.mock import MagicMock, patch

from vhf.ai.ai_selectors import selectStrat
from vhf.ai.selectors import selectorStrat
from vhf.models.portfolio import PortfolioSelector


class SelectorTest(unittest.TestCase):
    def test_selector_topk(self):
        sids = ["s1", "s2", "s3", "s4"]
        self.assertEqual(selectorStrat(sids, PortfolioSelector.topk, 2), ["s1", "s2"])

    def test_selector_bottomk(self):
        sids = ["s1", "s2", "s3", "s4"]
        self.assertEqual(selectorStrat(sids, PortfolioSelector.bottomk, 2), ["s3", "s4"])

    def test_ai_prompt_parser_no_available_ids_returns_empty(self):
        # When no available_ids are provided, selectStrat returns []
        self.assertEqual(selectStrat("pick something"), [])

    def test_ai_prompt_parser_empty_prompt_returns_available(self):
        # Empty prompt → return all available strategies unchanged
        available = ["s1", "s2", "s3"]
        self.assertEqual(selectStrat(None, available), available)
        self.assertEqual(selectStrat("", available), available)

    @patch.dict("os.environ", {}, clear=True)
    def test_ai_prompt_parser_no_api_key_falls_back_to_all(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        available = ["s1", "s2", "s3"]
        # Without API key, Claude call fails gracefully → returns all available
        result = selectStrat("pick growth strategies", available)
        self.assertEqual(result, available)

    @patch("vhf.db.operations.get_db_strat")
    def test_selector_ai_ranks_by_momentum(self, mock_get_strat):
        # s3 has best momentum (+50%), s1 worst (-10%)
        def strat_side_effect(sid):
            m = MagicMock()
            m.prices = {"s1": [100.0, 90.0], "s2": [100.0, 110.0], "s3": [100.0, 150.0]}[sid]
            return m

        mock_get_strat.side_effect = strat_side_effect
        sids = ["s1", "s2", "s3"]
        result = selectorStrat(sids, PortfolioSelector.ai, 2)
        # Should return top 2 by momentum: s3 (+50%), s2 (+10%)
        self.assertEqual(result, ["s3", "s2"])

    @patch("vhf.db.operations.get_db_strat")
    def test_selector_ai_falls_back_gracefully_on_db_error(self, mock_get_strat):
        mock_get_strat.side_effect = Exception("DB error")
        sids = ["s1", "s2", "s3"]
        # All strategies score 0 momentum, result is first k by iteration order
        result = selectorStrat(sids, PortfolioSelector.ai, 2)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(s in sids for s in result))


if __name__ == "__main__":
    unittest.main()
