import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
import time
from game.scavenging import ScavengingManager, ScavengeLevel, ScavengeAssignment, ScavengingUnavailableError

class FakeResponse:
    def __init__(self, text, url="https://pl227.plemiona.pl/game.php?village=1&screen=place&mode=scavenge"):
        self.text = text
        self.url = url

class FakeWrapper:
    def __init__(self, response_text):
        self.response = FakeResponse(response_text)
        self.last_h = "fake_h"
        self.post_calls = []

    def get_url(self, url):
        return self.response

    def post_api_data(self, village_id, action, params, data):
        self.post_calls.append({
            "village_id": village_id,
            "action": action,
            "params": params,
            "data": data
        })
        return {"success": True}

class TestScavengingManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            "gather_enabled": True,
            "gather_levels": [1, 2, 3],
            "gather_unit_priority": ["sword", "spear", "axe"],
            "gather_min_fill_ratio": 0.85,
            "gather_reserve_for_farm": {
                "light": 1.0,
                "marcher": 1.0
            },
            "gather_cooldown_minutes": 5
        }
        with open("tests/fixtures/scavenge_page.html", "r", encoding="utf-8") as f:
            self.html = f.read()
        self.wrapper = FakeWrapper(self.html)
        self.manager = ScavengingManager(village_id=1, config=self.config, wrapper=self.wrapper)

    def test_parse_available_units_excludes_reserved(self):
        """LK w HTML → nie powinna trafić do wyniku"""
        soup = BeautifulSoup(self.html, "html.parser")
        units = self.manager.parse_available_units(soup)
        
        self.assertIn("spear", units)
        self.assertIn("sword", units)
        self.assertIn("axe", units)
        self.assertNotIn("light", units) # Reserved 1.0
        self.assertEqual(units["spear"], 1000)

    def test_calculate_optimal_split_basic(self):
        """500 mieczy + 300 pik → 3 poziomy, sprawdź że suma units ≤ input"""
        units = {"sword": 500, "spear": 300}
        # Total carry: 500*15 + 300*25 = 7500 + 7500 = 15000
        levels = [
            ScavengeLevel(1, 1000, 0, False, False),
            ScavengeLevel(2, 2500, 0, False, False),
            ScavengeLevel(3, 5000, 0, False, False)
        ]
        
        assignments = self.manager.calculate_optimal_split(units, levels)
        
        # Greedy algorithm should fill higher levels first
        # Level 3 (5000) needs 5000 * 0.85 = 4250 carry
        # Level 2 (2500) needs 2500 * 0.85 = 2125 carry
        # Level 1 (1000) needs 1000 * 0.85 = 850 carry
        
        total_assigned = {"sword": 0, "spear": 0}
        for assign in assignments:
            for u, count in assign.units.items():
                total_assigned[u] += count
        
        self.assertLessEqual(total_assigned["sword"], 500)
        self.assertLessEqual(total_assigned["spear"], 300)
        self.assertTrue(len(assignments) > 0)

    def test_calculate_optimal_split_not_enough_units(self):
        """za mało jednostek → pomiń poziom z niskim fill_ratio"""
        units = {"axe": 10} # Carry: 10 * 10 = 100
        levels = [
            ScavengeLevel(1, 1000, 0, False, False) # Needs 850 carry for 0.85 ratio
        ]
        
        assignments = self.manager.calculate_optimal_split(units, levels)
        self.assertEqual(len(assignments), 0)

    def test_calculate_optimal_split_single_level(self):
        """tylko 1 wolny poziom → wszystko do niego (jeśli fill_ratio OK)"""
        units = {"spear": 100} # Carry: 2500
        levels = [
            ScavengeLevel(2, 2500, 0, False, False) # Needs 2500 * 0.85 = 2125
        ]
        
        assignments = self.manager.calculate_optimal_split(units, levels)
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].level_id, 2)
        # It should send all if it just reaches the ratio, or enough to fill it.
        # My implementation sends proportionally to what it has.
        self.assertEqual(assignments[0].units["spear"], 100)

    def test_cooldown_respected(self):
        """run() wywołane dwa razy szybko → drugi call nie wysyła requestów"""
        # First call
        self.manager.run()
        first_call_count = len(self.wrapper.post_calls)
        self.assertTrue(first_call_count > 0)
        
        # Second call immediately
        self.manager.run()
        self.assertEqual(len(self.wrapper.post_calls), first_call_count)

    def test_scavenge_unavailable(self):
        """Test behavior when scavenging is unavailable"""
        self.wrapper.response.url = "https://pl227.plemiona.pl/game.php?screen=place" # No mode=scavenge
        
        with self.assertRaises(ScavengingUnavailableError):
            self.manager.fetch_scavenge_page()

if __name__ == "__main__":
    unittest.main()
