"""Utility helpers for parsing Tribal Wars HTML responses."""

import json
import re
from typing import List


class Extractor:
    """
    Defines various non-compiled regexes for data retrieval
    TODO: use compiled various for CPU efficiency
    """
    @staticmethod
    def village_data(res):
        """
        Detects village data on a page
        """
        if type(res) != str:
            res = res.text
        grabber = re.search(r'var village = (.+);', res)
        if grabber:
            data = grabber.group(1)
            return json.loads(data, strict=False)

    @staticmethod
    def game_state(res):
        """
        Detects the game state that is available on most pages
        """
        if type(res) != str:
            res = res.text
        grabber = re.search(r'TribalWars\.updateGameData\((.+?)\);', res)
        if grabber:
            data = grabber.group(1)
            return json.loads(data, strict=False)

        # Some pages expose the same payload via other globals.
        alt_patterns = [
            r'var\s+game_data\s*=\s*(\{.+?\});',
            r'window\.game_data\s*=\s*(\{.+?\});',
        ]

        for pattern in alt_patterns:
            alt = re.search(pattern, res)
            if alt:
                try:
                    return json.loads(alt.group(1), strict=False)
                except ValueError:
                    pass

        # As a last resort, fall back to the village snippet if present.
        village_blob = Extractor.village_data(res)
        if village_blob:
            return {"village": village_blob}

    @staticmethod
    def building_data(res):
        """
        Fetches building data from the main building
        """
        if type(res) != str:
            res = res.text
        dre = re.search(r'(?s)BuildingMain.buildings = (\{.+?\});', res)
        if dre:
            return json.loads(dre.group(1), strict=False)

        return None

    @staticmethod
    def get_quests(res):
        """
        Gets quest data on almost any page
        """
        if type(res) != str:
            res = res.text
        get_quests = re.search(r'Quests.setQuestData\((\{.+?\})\);', res)
        if get_quests:
            result = json.loads(get_quests.group(1), strict=False)
            for quest in result:
                data = result[quest]
                if data['goals_completed'] == data['goals_total']:
                    return quest
        return None

    @staticmethod
    def get_quest_rewards(res):
        """
        Detects if there are rewards available for quests
        """
        if type(res) != str:
            res = res.text
        get_rewards = re.search(r'RewardSystem\.setRewards\(\s*(\[\{.+?\}\]),', res)
        rewards = []
        if get_rewards:
            result = json.loads(get_rewards.group(1), strict=False)
            for reward in result:
                if reward['status'] == "unlocked":
                    rewards.append(reward)
        # Return all off them
        return rewards

    @staticmethod
    def map_data(res):
        """
        Detects other villages on the map page
        """
        if type(res) != str:
            res = res.text
        data = re.search(r'(?s)TWMap.sectorPrefech = (\[(.+?)\]);', res)
        if data:
            result = json.loads(data.group(1), strict=False)
            return result

    @staticmethod
    def smith_data(res):
        """
        Gets smith data
        """
        if type(res) != str:
            res = res.text
        data = re.search(r'(?s)BuildingSmith.techs = (\{.+?\});', res)
        if data:
            result = json.loads(data.group(1), strict=False)
            return result
        return None

    @staticmethod
    def premium_data(res):
        """
        Detects data on the premium exchange page
        """
        if type(res) != str:
            res = res.text
        data = re.search(r'(?s)PremiumExchange.receiveData\((.+?)\);', res)
        if data:
            result = json.loads(data.group(1), strict=False)
            return result
        return None

    @staticmethod
    def recruit_data(res):
        """
        Fetches recruit data for the current building
        """
        if type(res) != str:
            res = res.text
        data = re.search(r'(?s)unit_managers.units = (\{.+?\});', res)
        if data:
            raw = data.group(1)
            quote_keys_regex = r'([\{\s,])(\w+)(:)'
            processed = re.sub(quote_keys_regex, r'\1"\2"\3', raw)
            result = json.loads(processed, strict=False)
            return result

    @staticmethod
    def units_in_village(res):
        """
        Detects all units in the village
        """
        if type(res) != str:
            res = res.text
        matches = re.search(r'<table id="units_home".*?</tr>(.*?)</tr>', res, re.DOTALL)
        # We get the start of the table and grab the 2nd row (Where "From this village" troops are located)
        if matches:
            table_content = matches.group(1)
            unit_matches = re.findall(r'class=\'unit-item unit-item-(.*?)\'[^>]*>(\d+)</td>', table_content)
            # Find all the tuples (name, quantity) under the class "unit-item unit-item-*troop_name*"
            units = [(re.sub(r'\s*tooltip\s*', '', unit_name), unit_quantity) for unit_name, unit_quantity in
                     unit_matches if int(unit_quantity) > 0]
            # Filter units with quantity = 0, also for the Paladin,
            # the name would be "knight tooltip", so we had to remove that.
            return units
        return []

    @staticmethod
    def active_building_queue(res):
        """
        Detects queued building entries
        """
        if type(res) != str:
            res = res.text
        builder = re.search('(?s)<table id="build_queue"(.+?)</table>', res)
        if not builder:
            return 0

        return builder.group(1).count('<a class="btn btn-cancel"')

    @staticmethod
    def active_recruit_queue(res):
        """
        Detects active recruitment entries
        """
        if type(res) != str:
            res = res.text
        builder = re.findall(r'(?s)TrainOverview\.cancelOrder\((\d+)\)', res)
        return builder

    @staticmethod
    def village_ids_from_game_data(res) -> List[str]:
        """
        Extracts village IDs from the TribalWars.updateGameData JSON.
        This is a fallback method when quickedit-vn elements are not present
        (e.g., when the server returns 'overview' instead of 'overview_villages').

        For multi-village accounts, this extracts all village IDs from the
        game_data["villages"] mapping when available.
        """
        if not isinstance(res, str):
            res = res.text

        # Extract the game data JSON
        game_data = Extractor.game_state(res)
        if not game_data:
            return []

        village_ids = []

        # Method 1: Try to get all villages from the villages mapping (multi-village accounts)
        # The game_data JSON contains a "villages" object with all owned villages
        if "villages" in game_data and isinstance(game_data["villages"], dict):
            # Villages mapping contains village_id as keys
            village_ids.extend([str(vid) for vid in game_data["villages"].keys()])

        # Method 2: Fallback to current village ID if no villages mapping exists
        # This handles edge cases and single-village accounts
        if not village_ids and "village" in game_data and "id" in game_data["village"]:
            village_id = str(game_data["village"]["id"])
            village_ids.append(village_id)

        return village_ids

    @staticmethod
    def village_ids_from_overview(res) -> List[str]:
        """
        Fetches villages from the overview page.
        Uses quickedit-vn elements as primary method with game_data JSON as fallback.
        """
        if not isinstance(res, str):
            res = res.text

        # Primary method: Look for quickedit-vn elements (works on overview_villages page)
        # Use two patterns to handle both attribute orders
        pattern1 = re.compile(
            r'<[a-zA-Z0-9]+\s+[^>]*?class=["\']([^"\']*\bquickedit-vn\b[^"\']*)["\'][^>]*?data-id=["\'](\d+)["\']',
            re.IGNORECASE
        )
        pattern2 = re.compile(
            r'<[a-zA-Z0-9]+\s+[^>]*?data-id=["\'](\d+)["\'][^>]*?class=["\']([^"\']*\bquickedit-vn\b[^"\']*)["\']',
            re.IGNORECASE
        )

        # Find all matches with their positions to preserve order
        all_matches = []

        for match in pattern1.finditer(res):
            all_matches.append((match.start(), match.group(2)))  # (position, id)

        for match in pattern2.finditer(res):
            all_matches.append((match.start(), match.group(1)))  # (position, id)

        # Sort by position and extract IDs, then deduplicate while preserving order
        all_matches.sort(key=lambda x: x[0])
        village_ids = list(dict.fromkeys([id for pos, id in all_matches]))

        # Fallback: If no villages found via quickedit-vn, try game_data JSON
        # This handles cases where server returns 'overview' instead of 'overview_villages'
        if not village_ids:
            village_ids = Extractor.village_ids_from_game_data(res)

        return village_ids

    @staticmethod
    def units_in_total(res):
        """
        Gets total amount of units in a village
        """
        if type(res) != str:
            res = res.text
        # hide units from other villages
        res = re.sub(r'(?s)<span class="village_anchor.+?</tr>', '', res)
        data = re.findall(r'(?s)class=\Wunit-item unit-item-([a-z]+)\W.+?(\d+)</td>', res)
        return data

    @staticmethod
    def get_farm_bag_state(res):
        """Extracts current and maximum farm bag values from the place screen."""
        if isinstance(res, str):
            html = res
        else:
            html = res.text

        text = re.sub(r'<span class="grey">\.</span>', '.', html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)

        matches = []
        # First try language specific anchor
        lang_match = re.findall(
            r'Erbeutete\s+Rohstoffe[^\d]*(\d[\d\.\,]*)\s*/\s*(\d[\d\.\,]*)',
            text,
            re.IGNORECASE,
        )
        matches.extend(lang_match)

        if not matches:
            # fallback to generic pattern capturing ratio around slash
            fallback = re.findall(
                r'(\d[\d\.\,]*)\s*/\s*(\d[\d\.\,]*)',
                text,
            )
            matches.extend(fallback)

        def _to_int(value):
            return int(value.replace('.', '').replace(',', '').strip())

        parsed = []
        for current, maximum in matches:
            try:
                parsed.append((_to_int(current), _to_int(maximum)))
            except ValueError:
                continue

        if not parsed:
            return None

        current, maximum = max(parsed, key=lambda item: item[0])
        if maximum <= 0:
            return None
        return {"current": current, "max": maximum}

    @staticmethod
    def attack_form(res):
        """
        Detects input fiels in the attack form
        ... because there are many :)
        """
        if type(res) != str:
            res = res.text
        data = re.findall(r'(?s)<input.+?name="(.+?)".+?value="(.*?)"', res)
        return data

    @staticmethod
    def attack_duration(res):
        """
        Detects the duration of an attack
        """
        if type(res) != str:
            res = res.text
        data = re.search(r'<span class="relative_time" data-duration="(\d+)"', res)
        if data:
            return int(data.group(1))
        return 0

    @staticmethod
    def report_table(res):
        """
        Fetches information from a report
        """
        if type(res) != str:
            res = res.text
        data = re.findall(r'(?s)class="report-link" data-id="(\d+)"', res)
        return data

    @staticmethod
    def get_daily_reward(res):
        """
        Detects if there are unopened daily rewards
        """
        if type(res) != str:
            res = res.text
        get_daily = re.search(r'DailyBonus.init\((\s+\{.*\}),', res)
        if not get_daily:
            return None
        try:
            payload = json.loads(get_daily.group(1))
        except ValueError:
            return None
        reward_count_unlocked = str(payload.get("reward_count_unlocked", ""))
        if (
                reward_count_unlocked
                and payload.get("chests")
                and payload["chests"].get(reward_count_unlocked, {}).get("is_collected")
        ):
            return reward_count_unlocked
        return None
