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


class BuildPromptClusterTest(unittest.TestCase):
    """Tests for the strategy-cluster section in _build_prompt."""

    def _ctx(self, sids: list[str], clusters: dict[str, int] | None = None) -> dict:
        return {
            "strategies": sids,
            "strategy_data": [
                {"strategy_id": s, "category": "equity", "metrics": {}}
                for s in sids
            ],
            **({"strategy_clusters": clusters} if clusters is not None else {}),
        }

    def test_section_present_when_clusters_provided(self):
        prompt = _build_prompt(self._ctx(["s1", "s2", "s3"], {"s1": 0, "s2": 0, "s3": 1}))
        self.assertIn("Strategy clusters", prompt)
        self.assertIn("Cluster 1:", prompt)
        self.assertIn("Cluster 2:", prompt)

    def test_section_absent_when_no_clusters(self):
        prompt = _build_prompt(self._ctx(["s1", "s2"]))
        self.assertNotIn("Strategy clusters", prompt)

    def test_guidance_text_present(self):
        prompt = _build_prompt(self._ctx(["s1", "s2"], {"s1": 0, "s2": 1}))
        self.assertIn("Diversify capital across clusters", prompt)
        self.assertIn("intra-cluster", prompt)

    def test_section_absent_on_wrong_length(self):
        # clusters dict has only 1 of 3 strategies — guard should suppress rendering
        prompt = _build_prompt(self._ctx(["s1", "s2", "s3"], {"s1": 0}))
        self.assertNotIn("Strategy clusters", prompt)

    def test_members_in_prompt_order(self):
        # strategies order: s1, s2, s3 — s1 and s3 share cluster 0
        prompt = _build_prompt(self._ctx(["s1", "s2", "s3"], {"s1": 0, "s2": 1, "s3": 0}))
        # s1 should appear before s3 within the cluster line (prompt iteration order)
        cluster1_line = [l for l in prompt.splitlines() if "Cluster 1:" in l][0]
        self.assertLess(cluster1_line.index("s1"), cluster1_line.index("s3"))


if __name__ == "__main__":
    unittest.main()
