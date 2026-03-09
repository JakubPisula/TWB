"""
Tests for test_village.
Migrated from root directory during AI-Update cleanup.
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from game.village import Village


class TestVillage(unittest.TestCase):

    def setUp(self):
        self.wrapper = MagicMock()
        self.village = Village(village_id='123', wrapper=self.wrapper)
        self.village.logger = MagicMock()
        self.village.config = {
            "farms": {
                "forced_peace_times": [
                    {
                        "start": "01.01.25 10:00:00",
                        "end": "01.01.25 12:00:00"
                    }
                ]
            }
        }

    @patch('game.village.datetime')
    def test_check_forced_peace_today(self, mock_datetime):
        # Arrange
        # Set the mocked "now" to a date that is inside the peace time window's day
        mock_datetime.now.return_value = datetime(2025, 1, 1, 9, 0, 0)
        mock_datetime.strptime.side_effect = lambda *args, **kw: datetime.strptime(*args, **kw)
        mock_datetime.today.return_value = mock_datetime.now.return_value

        # Act
        self.village.check_forced_peace()

        # Assert
        # This should be True but is False because of the bug
        self.assertTrue(self.village.forced_peace_today, "forced_peace_today should be True but is False")
        self.assertIsNotNone(self.village.forced_peace_today_start, "forced_peace_today_start should be set")

    @patch('game.village.datetime')
    def test_check_forced_peace_active(self, mock_datetime):
        # Arrange
        # Set the mocked "now" to a time that is inside the peace time window
        mock_datetime.now.return_value = datetime(2025, 1, 1, 11, 0, 0)
        mock_datetime.strptime.side_effect = lambda *args, **kw: datetime.strptime(*args, **kw)
        mock_datetime.today.return_value = mock_datetime.now.return_value

        # Act
        self.village.check_forced_peace()

        # Assert
        self.assertTrue(self.village.forced_peace, "forced_peace should be True")


if __name__ == '__main__':
    unittest.main()
