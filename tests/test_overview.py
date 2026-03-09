"""
Tests for test_overview.
Migrated from root directory during AI-Update cleanup.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pages.overview import OverviewPage, Point


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeWrapper:
    def __init__(self, text: str):
        self._text = text

    def get_url(self, url: str):
        return FakeResponse(self._text)


class OverviewPageParsingTests(unittest.TestCase):
    def test_parse_production_table_skips_unexpected_name_formats(self):
        html = """
        <html>
            <body>
                <table id="production_table">
                    <tr>
                        <td><span class="quickedit"></span><span data-id="123">Normal Village (500|500) K55</span></td>
                        <td>1.234</td>
                        <td>1.000 2.000 3.000</td>
                        <td>4000</td>
                        <td>100/200</td>
                    </tr>
                    <tr>
                        <td><span class="quickedit"></span><span data-id="456">Seltsames Dorf (Sondername 501|501) K55</span></td>
                        <td>2.345</td>
                        <td>4.000 5.000 6.000</td>
                        <td>5000</td>
                        <td>150/200</td>
                    </tr>
                </table>
            </body>
        </html>
        """
        page = OverviewPage(FakeWrapper(html))

        self.assertIn("123", page.villages_data)
        self.assertNotIn("456", page.villages_data)

        village = page.villages_data["123"]
        self.assertEqual(village.village_name, "Normal Village")
        self.assertEqual(village.coordinates, Point(500, 500))
        self.assertEqual(village.continent, "K55")
        self.assertEqual(village.points, 1234)


    def test_parse_production_table_handles_thousands_in_farm_and_capacity(self):
        html = """
        <html>
            <body>
                <table id=\"production_table\">
                    <tr>
                        <td><span class=\"quickedit\"></span><span data-id=\"789\">Village Name (400|400) K44</span></td>
                        <td>2.468</td>
                        <td>7.000 8.000 9.000</td>
                        <td>10.000</td>
                        <td>1.234/2.000</td>
                    </tr>
                </table>
            </body>
        </html>
        """

        page = OverviewPage(FakeWrapper(html))

        village = page.villages_data["789"]
        self.assertEqual(village.farm.current, 1234)
        self.assertEqual(village.farm.maximum, 2000)
        self.assertEqual(village.storage.capacity, 10000)


if __name__ == "__main__":
    unittest.main()
