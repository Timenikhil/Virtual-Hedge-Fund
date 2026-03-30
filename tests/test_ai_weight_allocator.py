import unittest
from unittest.mock import MagicMock, patch

from vhf.ai.ai_weight_allocator import _build_prompt, _parse_weights, allocate_weights


class ParseWeightsTest(unittest.TestCase):
    def test_parses_plain_json_array(self):
        result = _parse_weights("[0.5, 0.3, 0.2]", 3)
        self.assertEqual(result, [0.5, 0.3, 0.2])

    def test_parses_array_embedded_in_text(self):
        result = _parse_weights("Here are the weights: [0.4, 0.6]", 2)
        self.assertEqual(result, [0.4, 0.6])

    def test_raises_on_wrong_length(self):
        with self.assertRaises(ValueError):
            _parse_weights("[0.5, 0.5]", 3)

    def test_raises_on_unparseable_response(self):
        with self.assertRaises(ValueError):
            _parse_weights("I cannot determine weights.", 2)


class BuildPromptTest(unittest.TestCase):
    def test_includes_strategy_summaries(self):
        context = {
            "strategies": ["s1", "s2"],
            "strategy_data": [
                {"strategy_id": "s1", "name": "Momentum", "category": "equity",
                 "prices": [100.0, 110.0], "latest_price": 110.0, "price_count": 2},
                {"strategy_id": "s2", "name": "MeanRev", "category": "equity",
                 "prices": [], "latest_price": None, "price_count": 0},
            ],
        }
        prompt = _build_prompt(context)
        self.assertIn("s1", prompt)
        self.assertIn("s2", prompt)
        self.assertIn("2", prompt)  # expected_len mention

    def test_includes_current_weights(self):
        context = {
            "strategies": ["s1", "s2"],
            "current_weights": [0.6, 0.4],
            "strategy_data": [],
        }
        prompt = _build_prompt(context)
        self.assertIn("Current weights", prompt)


class AllocateWeightsTest(unittest.TestCase):
    def _make_message(self, text: str):
        content_block = MagicMock()
        content_block.text = text
        message = MagicMock()
        message.content = [content_block]
        return message

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("vhf.ai.ai_weight_allocator.anthropic.Anthropic")
    def test_returns_parsed_weights(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_message("[0.6, 0.4]")

        result = allocate_weights({
            "strategies": ["s1", "s2"],
            "strategy_data": [],
        })
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0], 0.6)
        self.assertAlmostEqual(result[1], 0.4)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("vhf.ai.ai_weight_allocator.anthropic.Anthropic")
    def test_raises_on_empty_content(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = []
        mock_client.messages.create.return_value = mock_response

        with self.assertRaises(ValueError):
            allocate_weights({"strategies": ["s1"], "strategy_data": []})

    def test_raises_on_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with self.assertRaises(ValueError, msg="ANTHROPIC_API_KEY"):
                allocate_weights({"strategies": ["s1"], "strategy_data": []})

    def test_raises_on_empty_strategies(self):
        with self.assertRaises(ValueError):
            allocate_weights({"strategies": [], "strategy_data": []})


if __name__ == "__main__":
    unittest.main()
