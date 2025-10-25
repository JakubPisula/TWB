import unittest

from game.warehouse_balancer import ResourceCoordinator


class WarehouseBalancerSettingsTest(unittest.TestCase):
    def test_invalid_mode_falls_back_to_requests_only(self):
        config = {"balancer": {"mode": "invalid"}}

        with self.assertLogs("ResourceCoordinator", level="WARNING") as captured:
            coordinator = ResourceCoordinator(wrapper=None, config=config)

        self.assertEqual("requests_only", coordinator.settings["mode"])
        self.assertTrue(
            any("Unknown balancer mode" in message for message in captured.output)
        )


if __name__ == "__main__":
    unittest.main()
