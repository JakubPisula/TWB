"""
Tests for test_smart_farming.
Migrated from root directory during AI-Update cleanup.
"""
import unittest
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

    def test_smart_fill_with_knight(self):
        # Template: 10 Spear (250) + 1 Knight (100) = 350 Capacity
        # Have: 0 Knight, 0 Spear, 100 Light (80)
        # Expected: ~5 Light (400) or 4 Light (320) + 1 Light = 5
        # 350 / 80 = 4.375 -> 5 Light.

        template = {"spear": 10, "knight": 1}
        self.tm.troops = {"spear": "0", "knight": "0", "light": "100"}

        result = self.am.get_smart_troops(template)

        self.assertEqual(result.get("light"), 5)

    def test_zero_capacity_template_returns_none(self):
        """
        FIX: Templates with only zero-capacity units (spy, ram, catapult, snob)
        should return None so send_farm() performs the normal availability check.
        This prevents sending attacks with unavailable troops.
        """
        # Template: 5 Spies (0 capacity each) = 0 total capacity
        template = {"spy": 5}
        self.tm.troops = {"spy": "10", "spear": "100"}

        result = self.am.get_smart_troops(template)

        # Should return None, NOT the template
        self.assertIsNone(result)

    def test_zero_capacity_rams_template_returns_none(self):
        """
        Templates with only rams should also return None.
        """
        template = {"ram": 10}
        self.tm.troops = {"ram": "5", "light": "50"}

        result = self.am.get_smart_troops(template)

        self.assertIsNone(result)

    def test_mixed_zero_and_carry_capacity(self):
        """
        Templates with mix of zero-capacity and carry-capacity units
        should work normally (only the carry capacity counts).
        """
        # Template: 5 Spies (0) + 10 Light (800) = 800 capacity
        # Have: 3 Spies, 5 Light
        # Expected: use available spies + fill with light
        template = {"spy": 5, "light": 10}
        self.tm.troops = {"spy": "3", "light": "20", "spear": "100"}

        result = self.am.get_smart_troops(template)

        # Should have the 3 available spies and enough light to reach 800 capacity
        self.assertEqual(result.get("spy"), 3)
        self.assertEqual(result.get("light"), 10)  # 10 * 80 = 800

    def test_no_troops_available_returns_none(self):
        """
        When no troops are available at all, should return None.
        """
        template = {"axe": 20}
        self.tm.troops = {}

        result = self.am.get_smart_troops(template)

        self.assertIsNone(result)

    def test_only_zero_capacity_troops_available(self):
        """
        When only zero-capacity troops are available, should return None.
        """
        template = {"axe": 20}  # Target: 200 capacity
        self.tm.troops = {"spy": "100", "ram": "50"}

        result = self.am.get_smart_troops(template)

        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
