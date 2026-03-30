import unittest

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

    def test_ai_prompt_parser_deduplicates(self):
        prompt = "s1, s2 s2\ns3"
        self.assertEqual(selectStrat(prompt), ["s1", "s2", "s3"])


if __name__ == "__main__":
    unittest.main()
