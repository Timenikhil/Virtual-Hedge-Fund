import unittest
from unittest.mock import MagicMock, patch

from vhf.ai.ai_selectors import _parse_selector_response, selectSelector
from vhf.models.portfolio import PortfolioSelector


class ParseSelectorResponseTest(unittest.TestCase):
    def test_parses_topk(self):
        selector, k = _parse_selector_response('{"selector": "topk", "k": 5}', n=10)
        self.assertEqual(selector, PortfolioSelector.topk)
        self.assertEqual(k, 5)

    def test_parses_bottomk(self):
        selector, k = _parse_selector_response('{"selector": "bottomk", "k": 3}', n=10)
        self.assertEqual(selector, PortfolioSelector.bottomk)
        self.assertEqual(k, 3)

    def test_clamps_k_to_n(self):
        _, k = _parse_selector_response('{"selector": "topk", "k": 999}', n=4)
        self.assertEqual(k, 4)

    def test_clamps_k_minimum_to_1(self):
        _, k = _parse_selector_response('{"selector": "topk", "k": 0}', n=4)
        self.assertEqual(k, 1)

    def test_parses_json_embedded_in_text(self):
        selector, k = _parse_selector_response(
            'Based on performance: {"selector": "bottomk", "k": 2}', n=5
        )
        self.assertEqual(selector, PortfolioSelector.bottomk)
        self.assertEqual(k, 2)

    def test_unknown_selector_defaults_to_topk(self):
        selector, _ = _parse_selector_response('{"selector": "random", "k": 3}', n=5)
        self.assertEqual(selector, PortfolioSelector.topk)

    def test_raises_on_no_json(self):
        with self.assertRaises(ValueError):
            _parse_selector_response("no json here at all", n=5)


class SelectSelectorTest(unittest.TestCase):
    def _make_portfolio(self, strategies):
        p = MagicMock()
        p.strategies = strategies
        return p

    def _make_strat(self, prices):
        s = MagicMock()
        s.prices = prices
        s.name = "test"
        return s

    def _make_message(self, text: str):
        content_block = MagicMock()
        content_block.text = text
        msg = MagicMock()
        msg.content = [content_block]
        return msg

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("vhf.ai.ai_selectors.anthropic.Anthropic")
    @patch("vhf.db.operations.get_db_strat")
    @patch("vhf.db.operations.get_db_portfolio_id")
    def test_returns_claude_recommendation(
        self, mock_portfolio, mock_strat, mock_anthropic_cls
    ):
        mock_portfolio.return_value = self._make_portfolio(["s1", "s2", "s3"])
        mock_strat.return_value = self._make_strat([100.0, 120.0])
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_message(
            '{"selector": "bottomk", "k": 2}'
        )

        selector, k = selectSelector(1)
        self.assertEqual(selector, PortfolioSelector.bottomk)
        self.assertEqual(k, 2)

    @patch("vhf.db.operations.get_db_portfolio_id")
    def test_falls_back_when_portfolio_load_fails(self, mock_portfolio):
        mock_portfolio.side_effect = Exception("DB down")
        selector, k = selectSelector(99)
        self.assertEqual(selector, PortfolioSelector.topk)
        self.assertEqual(k, 10)

    @patch.dict("os.environ", {}, clear=True)
    @patch("vhf.db.operations.get_db_strat")
    @patch("vhf.db.operations.get_db_portfolio_id")
    def test_falls_back_when_api_key_missing(self, mock_portfolio, mock_strat):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        mock_portfolio.return_value = self._make_portfolio(["s1", "s2"])
        mock_strat.return_value = self._make_strat([100.0, 105.0])

        selector, k = selectSelector(1)
        self.assertEqual(selector, PortfolioSelector.topk)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("vhf.ai.ai_selectors.anthropic.Anthropic")
    @patch("vhf.db.operations.get_db_strat")
    @patch("vhf.db.operations.get_db_portfolio_id")
    def test_falls_back_when_claude_call_fails(
        self, mock_portfolio, mock_strat, mock_anthropic_cls
    ):
        mock_portfolio.return_value = self._make_portfolio(["s1", "s2"])
        mock_strat.return_value = self._make_strat([100.0, 105.0])
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("network error")

        selector, k = selectSelector(1)
        self.assertEqual(selector, PortfolioSelector.topk)

    @patch("vhf.db.operations.get_db_portfolio_id")
    def test_empty_portfolio_returns_topk_default(self, mock_portfolio):
        mock_portfolio.return_value = self._make_portfolio([])
        selector, k = selectSelector(1)
        self.assertEqual(selector, PortfolioSelector.topk)
        self.assertEqual(k, 10)


if __name__ == "__main__":
    unittest.main()
