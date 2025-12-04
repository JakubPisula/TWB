import unittest
from unittest.mock import MagicMock
from game.attack import AttackManager
from game.troopmanager import TroopManager

class TestSmartFarming(unittest.TestCase):
    def setUp(self):
        self.tm = TroopManager()
        self.tm.troops = {}
        # self.tm.carry_capacity is set in class definition

        self.am = AttackManager(troopmanager=self.tm)
        self.am.smart_farming = True
        self.am.smart_farming_priority = ["light", "spear", "axe", "sword"]

    def test_smart_fill_partial_template(self):
        # Template: 20 Axe (200 capacity)
        # Have: 10 Axe, 100 Spear
        # Expected: 10 Axe (100 cap), + 4 Spear (100 cap) = 200 cap

        template = {"axe": 20}
        self.tm.troops = {"axe": "10", "spear": "100", "sword": "0"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("axe"), 10)
        self.assertEqual(result.get("spear"), 4)
        self.assertEqual(sum(result.values()), 14)

    def test_smart_fill_no_template_units(self):
        # Template: 20 Axe (200 capacity)
        # Have: 0 Axe, 100 Spear
        # Expected: 8 Spear (200 cap)

        template = {"axe": 20}
        self.tm.troops = {"axe": "0", "spear": "100", "sword": "0"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("axe", 0), 0)
        self.assertEqual(result.get("spear"), 8)

    def test_smart_fill_priority(self):
        # Template: 20 Axe (200 capacity)
        # Have: 0 Axe, 10 Light (800 cap), 100 Spear (2500 cap)
        # Priority: Light > Spear
        # Expected: 3 Light (240 cap > 200 cap)

        template = {"axe": 20}
        self.tm.troops = {"axe": "0", "light": "10", "spear": "100"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("light"), 3)
        self.assertEqual(result.get("spear", 0), 0)

    def test_smart_fill_fallback(self):
        # Template: 20 Axe (200 capacity)
        # Have: 0 Axe, 0 Light, 100 Sword (15 cap)
        # Need 200.
        # Sword needed: 200/15 = 13.33 -> 14.

        template = {"axe": 20}
        self.tm.troops = {"axe": "0", "light": "0", "sword": "100"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("sword"), 14)

    def test_smart_fill_insufficient(self):
        # Template: 20 Axe (200 capacity)
        # Have: 5 Spear (125 cap)
        # Expected: 5 Spear (Send what we have)

        template = {"axe": 20}
        self.tm.troops = {"spear": "5"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("spear"), 5)

if __name__ == '__main__':
    unittest.main()
