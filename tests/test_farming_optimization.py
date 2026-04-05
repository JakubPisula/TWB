import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from game.attack import AttackManager
from game.troopmanager import TroopManager
from core.database import DatabaseManager

class TestFarmingOptimization(unittest.TestCase):
    def setUp(self):
        # Mocking TroopManager and its attributes
        self.tm = TroopManager()
        self.tm.troops = {"light": "100"}
        # Ensure carry_capacity is set (usually in the class, but we'll be sure)
        self.tm.carry_capacity = {"light": 80, "spear": 25, "axe": 10, "sword": 15}
        
        # AttackManager for village 100
        self.am = AttackManager(village_id="100", troopmanager=self.tm)
        self.am.smart_farming = True
        self.am.min_farm_capacity = 50
        self.am.min_farm_units = 1

    def test_get_smart_troops_with_max_loot_cap(self):
        """
        Verify that get_smart_troops respects the max_loot_cap parameter.
        Test scenario: 
        Template capacity: 800 (10 Light)
        Max loot cap: 200
        Expected: Bot should only send 3 Light (240 capacity) instead of 10.
        """
        template = {"light": 10}
        # Normal smart fill would take 10 light
        res_normal = self.am.get_smart_troops(template)
        self.assertEqual(res_normal.get("light"), 10)
        
        # With cap 200: (200 / 80 = 2.5 -> ceil = 3)
        res_capped = self.am.get_smart_troops(template, max_loot_cap=200)
        self.assertEqual(res_capped.get("light"), 3, "Should have capped light at 3 to fit ~200 loot")

    @patch('core.database.DatabaseManager.get_predicted_resources')
    def test_send_farm_skips_if_predicted_loot_below_min(self, mock_get_res):
        """
        Verify that send_farm skips an attack if the predicted loot is below min_farm_capacity.
        """
        target = {"id": "200"}
        template = {"light": 1}
        
        # Predicted resources = 10 (below min_farm_capacity=50)
        mock_get_res.return_value = {"wood": 4, "stone": 3, "iron": 3}
        
        # send_farm returns 1 on success, -1 on missing troops, 0 on skip/failure
        result = self.am.send_farm((target, 0), template)
        
        self.assertEqual(result, 0)
        # We don't want to see "Attacking" which would mean it didn't skip
        # Note: In real setup, we'd check if attack() was called, but here we check result.

    @patch('game.farm_optimizer.FarmOptimizer.evaluate')
    @patch('game.attack.AttackCache.get_cache')
    def test_can_attack_respects_optimizer_contested(self, mock_cache, mock_eval):
        """
        Verify that can_attack skips targets flagged as contested/waiting by FarmOptimizer.
        """
        vid = "300"
        # Fix: include 'safe': True which is checked in can_attack
        mock_cache.return_value = {
            "last_attack": int(datetime.utcnow().timestamp()) - 100,
            "safe": True,
            "scout": True,
            "high_profile": False
        }
        
        # Imagine optimizer recommends waiting 3600s because it's contested
        mock_eval.return_value = (3600, "contested")
        
        # Since last_attack was only 100s ago, and wait is 3600s, it should return False
        result = self.am.can_attack(vid)
        
        self.assertFalse(result, "Should skip target because optimizer recommended wait")

    @patch('core.database.DatabaseManager._session')
    def test_database_prediction_logic(self, mock_session):
        """
        Test the math inside DatabaseManager.get_predicted_resources.
        """
        # Patch HAS_SQLALCHEMY directly in the module
        with patch('core.database.HAS_SQLALCHEMY', True):
            # --- MOCK DATA ---
            mock_session_instance = MagicMock(name="SessionInstance")
            mock_session.return_value = mock_session_instance
            
            # Latest report (1 hour ago)
            # Scout saw 1000 wood, 1000 stone, 1000 iron
            mock_report = MagicMock(name="MockReport")
            mock_report.created_at = datetime.utcnow() - timedelta(hours=1)
            mock_report.scout_wood = 1000
            mock_report.scout_stone = 1000
            mock_report.scout_iron = 1000
            mock_report.scout_buildings = {"storage": 5} # Cap will be ~2200
            
            # Village production: 100/h each
            mock_village = MagicMock(name="MockVillage")
            mock_village.wood_prod = 100
            mock_village.stone_prod = 100
            mock_village.iron_prod = 100
            
            # Subsequent attacks: 1 attack took 200 each
            mock_attack = MagicMock(name="MockAttack")
            mock_attack.loot_wood = 200
            mock_attack.loot_stone = 200
            mock_attack.loot_iron = 200
            mock_attack.sent_at = datetime.utcnow() - timedelta(minutes=30)
            
            # Setup Query chain
            # We need to import the real classes for type checking in DatabaseManager
            import core.database as db
            
            def mock_query(model):
                q = MagicMock(name=f"Query[{model.__name__}]")
                if model == db.DBReport:
                    q.filter.return_value.order_by.return_value.first.return_value = mock_report
                elif model == db.DBAttack:
                    q.filter.return_value.all.return_value = [mock_attack]
                return q
            
            mock_session_instance.query.side_effect = mock_query
            mock_session_instance.get.return_value = mock_village
            
            # --- EXECUTE ---
            # Formula: 1000 (base) + 100 (prod * 1h) - 200 (loot) = 900
            res = DatabaseManager.get_predicted_resources("200")
            
            self.assertEqual(res.get("wood"), 900, f"Predicted resources mismatch: {res}")
            self.assertEqual(res.get("stone"), 900)
            self.assertEqual(res.get("iron"), 900)

if __name__ == '__main__':
    unittest.main()
