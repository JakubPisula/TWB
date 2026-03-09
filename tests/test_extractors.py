"""
Tests for test_extractors.
Migrated from root directory during AI-Update cleanup.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.extractors import Extractor


class ExtractorVillageTests(unittest.TestCase):
    def test_village_ids_handles_attribute_order(self):
        html = (
            '<span class="quickedit-vn" data-id="14818">A</span>'
            '<span data-id="13457" class="quickedit-vn">B</span>'
            '<span class="other quickedit-vn" data-id="14818">Duplicate</span>'
        )

        village_ids = Extractor.village_ids_from_overview(html)

        self.assertEqual(village_ids, ["14818", "13457"])

    def test_village_ids_ignores_spans_without_class(self):
        html = (
            '<span data-id="11111">Ignored</span>'
            '<span data-id="22222" class="quickedit-vn extra" data-length="32">Valid</span>'
            '<span class="quickedit-vn" data-id="33333" data-length="32"\n             data-foo="bar">ValidWithNewline</span>'
            "<span class='quickedit-vn extra' data-id='44444'>SingleQuotes</span>"
            '<SPAN CLASS="quickedit-vn" DATA-ID="55555">Uppercase</SPAN>'
        )

        village_ids = Extractor.village_ids_from_overview(html)

        self.assertEqual(village_ids, ["22222", "33333", "44444", "55555"])

    def test_village_ids_falls_back_to_game_state(self):
        html = (
            "<script>TribalWars.updateGameData({\"village\":{\"id\":11111},"
            "\"villages\":{\"11111\":{},\"22222\":{}}});</script>"
        )

        village_ids = Extractor.village_ids_from_overview(html)

        self.assertEqual(village_ids, ["11111", "22222"])


class ExtractorDailyRewardTests(unittest.TestCase):
    def test_get_daily_reward_returns_none_when_block_missing(self):
        html = "<html><body><div>No daily bonus here</div></body></html>"

        reward = Extractor.get_daily_reward(html)

        self.assertIsNone(reward)


if __name__ == "__main__":
    unittest.main()
