"""
Attack manager
Sounds dangerous but it just sends farms
"""

import json
import logging
import time
from datetime import datetime
from datetime import timedelta

from core.extractors import Extractor
from core.filemanager import FileManager


class AttackManager:
    """
    Attackmanager class
    """
    map = None
    village_id = None
    troopmanager = None
    wrapper = None
    targets = {}
    logger = logging.getLogger("Attacks")
    max_farms = 15
    template = {}
    extra_farm = []
    repman = None
    target_high_points = False
    farm_radius = 50
    farm_minpoints = 0
    farm_maxpoints = 1000
    ignored = []

    # Configures the amount of spies used to detect if villages are safe to farm
    scout_farm_amount = 5

    forced_peace_time = None

    farm_bag_limit_enabled = False
    farm_bag_block_scouts = True
    farm_bag_limit_margin = 0.0
    last_farm_bag_state = None
    _farm_bag_limit_reached = False
    _farm_bag_last_log = 0

    # blocks villages which cannot be attacked at the moment (too low points, beginners protection etc..)
    _unknown_ignored = []

    # Don't mess with these they are in the config file
    farm_high_prio_wait = 1200
    farm_default_wait = 3600
    farm_low_prio_wait = 7200

    def __init__(self, wrapper=None, village_id=None, troopmanager=None, map=None):
        """
        Create the attack manager
        """
        self.wrapper = wrapper
        self.village_id = village_id
        self.troopmanager = troopmanager
        self.map = map

    def enough_in_village(self, units):
        """
        Checks if there are enough troops in a village
        """
        for unit in units:
            if unit not in self.troopmanager.troops:
                return f"{unit} (0/{units[unit]})"
            if units[unit] > int(self.troopmanager.troops[unit]):
                return f"{unit} ({self.troopmanager.troops[unit]}/{units[unit]})"
        return False

    def run(self):
        """
        Run the farming logic
        """
        if not self.troopmanager.can_attack or self.troopmanager.troops == {}:
            # Disable farming is disabled in config or no troops available
            return False
        if self.farm_bag_limit_enabled and self._farm_bag_limit_reached:
            self._refresh_farm_bag_state()
            if not self._farm_bag_limit_reached:
                self.logger.debug(
                    "Farm bag limit cleared after refreshing place screen"
                )
        self.get_targets()
        ignored = []
        # Limits the amount of villages that are farmed from the current village
        for target in self.targets[0: self.max_farms]:
            if type(self.template) == list:
                f = False
                for template in self.template:
                    if template in ignored:
                        continue
                    out_res = self.send_farm(target, template)
                    if out_res == 1:
                        f = True
                        break
                    elif out_res == -1:
                        ignored.append(template)
                if not f:
                    continue
            else:
                out_res = self.send_farm(target, self.template)
                if out_res == -1:
                    break

    def send_farm(self, target, template):
        """
        Send a farming run
        """
        target, _ = target
        if self.farm_bag_limit_enabled and self._farm_bag_limit_reached:
            self.logger.debug("Skipping farm target because farm bag limit was reached earlier")
            return 0
        missing = self.enough_in_village(template)
        if not missing:
            cached = self.can_attack(vid=target["id"], clear=False)
            if cached:
                attack_result = self.attack(target["id"], troops=template)
                if attack_result == "forced_peace":
                    return 0
                if attack_result == "farm_bag_full":
                    return 0
                self.logger.info(
                    "Attacking %s -> %s (%s)" ,self.village_id, target["id"], str(template)
                )
                self.wrapper.reporter.report(
                    self.village_id,
                    "TWB_FARM",
                    "Attacking %s -> %s (%s)"
                    % (self.village_id, target["id"], str(template)),
                    )
                if attack_result:
                    for u in template:
                        self.troopmanager.troops[u] = str(
                            int(self.troopmanager.troops[u]) - template[u]
                        )
                    self.attacked(
                        target["id"],
                        scout=True,
                        safe=True,
                        high_profile=cached["high_profile"]
                        if type(cached) == dict
                        else False,
                        low_profile=cached["low_profile"]
                        if type(cached) == dict and "low_profile" in cached
                        else False,
                    )
                    return 1
                else:
                    self.logger.debug(
                        "Ignoring target %s because unable to attack", target["id"]
                    )
                    self._unknown_ignored.append(target["id"])
        else:
            self.logger.debug(
                "Not sending additional farm because not enough units: %s", missing
            )
            return -1
        return 0

    def get_targets(self):
        """
        Gets all possible farming targets based on distance
        """
        output = []
        my_village = (
            self.map.villages[self.village_id]
            if self.village_id in self.map.villages
            else None
        )

        # --- LOGGING IMPROVEMENT: Consolidate ignore messages ---
        ignored_reasons = {
            "player_owned": 0,
            "max_points": 0,
            "min_points": 0,
            "higher_points": 0,
            "unknown_ignored": 0,
            "night_bonus": 0,
            "too_far": 0,
        }

        for vid in self.map.villages:
            village = self.map.villages[vid]
            if village["owner"] != "0" and vid not in self.extra_farm:
                if vid not in self.ignored:
                    ignored_reasons["player_owned"] += 1
                    self.ignored.append(vid)
                continue
            if my_village and "points" in my_village and "points" in village:
                if village["points"] >= self.farm_maxpoints:
                    if vid not in self.ignored:
                        ignored_reasons["max_points"] += 1
                        self.ignored.append(vid)
                    continue
                if village["points"] <= self.farm_minpoints:
                    if vid not in self.ignored:
                        ignored_reasons["min_points"] += 1
                        self.ignored.append(vid)
                    continue
                if (
                        village["points"] >= my_village["points"]
                        and not self.target_high_points
                ):
                    if vid not in self.ignored:
                        ignored_reasons["higher_points"] += 1
                        self.ignored.append(vid)
                    continue
                if vid in self._unknown_ignored:
                    ignored_reasons["unknown_ignored"] += 1
                    continue
            if village["owner"] != "0":
                get_h = time.localtime().tm_hour
                if get_h in range(0, 8) or get_h == 23:
                    ignored_reasons["night_bonus"] += 1
                    continue
            distance = self.map.get_dist(village["location"])
            if distance > self.farm_radius:
                if vid not in self.ignored:
                    ignored_reasons["too_far"] += 1
                    self.ignored.append(vid)
                continue
            if vid in self.ignored:
                self.logger.debug("Removed %s from farm ignore list", vid)
                self.ignored.remove(vid)

            output.append([village, distance])

        # --- LOGGING IMPROVEMENT: Log summary instead of spam ---
        ignored_count = len(self.ignored)
        ignored_details = ", ".join(f"{reason}: {count}" for reason, count in ignored_reasons.items() if count > 0)
        self.logger.info(
            "Farm targets: %d. Ignored targets: %d (%s)",
            len(output),
            ignored_count,
            ignored_details if ignored_details else "none"
        )
        # --- END LOGGING IMPROVEMENT ---

        self.targets = sorted(output, key=lambda x: x[1])

    def attacked(self, vid, scout=False, high_profile=False, safe=True, low_profile=False):
        """
        The farm was sent and this is a callback on what happened
        """
        cache_entry = {
            "scout": scout,
            "safe": safe,
            "high_profile": high_profile,
            "low_profile": low_profile,
            "last_attack": int(time.time()),
        }
        AttackCache.set_cache(vid, cache_entry)

    def scout(self, vid):
        """
        Attempt to send scouts to a farm
        """
        if (
                self.farm_bag_limit_enabled
                and self._farm_bag_limit_reached
                and self.farm_bag_block_scouts
        ):
            self.logger.debug("Skipping scout because farm bag limit reached")
            return False
        if "spy" not in self.troopmanager.troops or int(self.troopmanager.troops["spy"]) < self.scout_farm_amount:
            self.logger.debug(
                "Cannot scout %s at the moment because insufficient unit: spy", vid
            )
            return False
        troops = {"spy": self.scout_farm_amount}
        result = self.attack(
            vid,
            troops=troops,
            check_bag_limit=self.farm_bag_block_scouts,
        )
        if not result or result in ("farm_bag_full", "forced_peace"):
            return False
        self.attacked(vid, scout=True, safe=False)
        return True

    def can_attack(self, vid, clear=False):
        """
        Checks if it is safe en engage
        If not an amount of 5 scouts will be sent
        """
        cache_entry = AttackCache.get_cache(vid)

        if cache_entry and cache_entry["last_attack"]:
            last_attack = datetime.fromtimestamp(cache_entry["last_attack"])
            now = datetime.now()
            if last_attack < now - timedelta(hours=12):
                self.logger.debug(f"Attacked long ago %s, trying scout attack", {last_attack})
                if self.scout(vid):
                    return False

        if not cache_entry:
            status = self.repman.safe_to_engage(vid)
            if status == 1:
                return True

            if self.troopmanager.can_scout:
                self.scout(vid)
                return False
            self.logger.warning(
                "%s will be attacked but scouting is not possible (yet), going in blind!", vid
            )
            return True

        if not cache_entry["safe"] or clear:
            if cache_entry["scout"] and self.repman:
                status = self.repman.safe_to_engage(vid)
                if status == -1:
                    self.logger.info(
                        "Checking %s: scout report not yet available", vid
                    )
                    return False
                if status == 0:
                    if cache_entry["last_attack"] + self.farm_low_prio_wait * 2 > int(time.time()):
                        self.logger.info(f"{vid}: Old scout report found ({cache_entry['last_attack']}), re-scouting")
                        self.scout(vid)
                        return False
                    else:
                        self.logger.info(
                            "%s: scout report noted enemy units, ignoring", vid
                        )
                        return False
                self.logger.info(
                    "%s: scout report noted no enemy units, attacking", vid
                )
                return True

            self.logger.debug(
                "%s will be ignored for attack because unsafe, set safe:true to override", vid
            )
            return False

        if not cache_entry["scout"] and self.troopmanager.can_scout:
            self.scout(vid)
            return False
        min_time = self.farm_default_wait
        if cache_entry["high_profile"]:
            min_time = self.farm_high_prio_wait
        if "low_profile" in cache_entry and cache_entry["low_profile"]:
            min_time = self.farm_low_prio_wait

        if cache_entry and self.repman:
            res_left, res = self.repman.has_resources_left(vid)
            total_loot = 0
            for x in res:
                total_loot += int(res[x])

            if res_left and total_loot > 100:
                self.logger.debug(f"Draining farm of resources! Sending attack to get {res}.")
                min_time = int(self.farm_high_prio_wait / 2)

        if cache_entry["last_attack"] + min_time > int(time.time()):
            self.logger.debug(
                "%s will be ignored because of previous attack (%d sec delay between attacks)",
                vid, min_time
            )
            return False
        return cache_entry

    def has_troops_available(self, troops):
        for t in troops:
            if (
                    t not in self.troopmanager.troops
                    or int(self.troopmanager.troops[t]) < troops[t]
            ):
                return False
        return True

    def attack(self, vid, troops=None, check_bag_limit=True):
        """
        Send a TW attack
        """
        url = f"game.php?village={self.village_id}&screen=place&target={vid}"
        pre_attack = self.wrapper.get_url(url)
        if not pre_attack:
            return False
        bag_state = Extractor.get_farm_bag_state(pre_attack)
        if bag_state:
            self.last_farm_bag_state = bag_state
            if self.farm_bag_limit_enabled and check_bag_limit:
                margin = max(0.0, min(1.0, self.farm_bag_limit_margin or 0.0))
                threshold = bag_state["max"] * (1 - margin)
                if bag_state["current"] >= threshold:
                    self._farm_bag_limit_reached = True
                    self._log_farm_bag_block(bag_state)
                    self._push_farm_bag_state()
                    return "farm_bag_full"
            if bag_state["current"] < bag_state["max"]:
                self._farm_bag_limit_reached = False
        pre_data = {}
        for u in Extractor.attack_form(pre_attack):
            k, v = u
            pre_data[k] = v
        if troops:
            pre_data.update(troops)
        else:
            pre_data.update(self.troopmanager.troops)

        if vid not in self.map.map_pos:
            return False

        x, y = self.map.map_pos[vid]
        post_data = {"x": x, "y": y, "target_type": "coord", "attack": "Aanvallen"}
        pre_data.update(post_data)

        confirm_url = f"game.php?village={self.village_id}&screen=place&try=confirm"
        conf = self.wrapper.post_url(url=confirm_url, data=pre_data)
        if '<div class="error_box">' in conf.text:
            return False
        duration = Extractor.attack_duration(conf)
        if self.forced_peace_time:
            now = datetime.now()
            if now + timedelta(seconds=duration) > self.forced_peace_time:
                self.logger.info("Attack would arrive after the forced peace timer, not sending attack!")
                return "forced_peace"

        self.logger.info(
            "[Attack] %s -> %s duration %f.1 h", self.village_id, vid, duration / 3600
        )

        confirm_data = {}
        for u in Extractor.attack_form(conf):
            k, v = u
            if k == "support":
                continue
            confirm_data[k] = v
        new_data = {"building": "main", "h": self.wrapper.last_h}
        confirm_data.update(new_data)
        # The extractor doesn't like the empty cb value, and mistakes its value for x. So I add it here.
        if "x" not in confirm_data:
            confirm_data["x"] = x

        result = self.wrapper.get_api_action(
            village_id=self.village_id,
            action="popup_command",
            params={"screen": "place"},
            data=confirm_data,
        )

        self._push_farm_bag_state()
        return result

    def _push_farm_bag_state(self):
        if not self.last_farm_bag_state:
            return
        current = self.last_farm_bag_state.get("current")
        maximum = self.last_farm_bag_state.get("max")
        if current is None or maximum is None:
            return
        pct = (current / maximum) if maximum else 0
        payload = {
            "current": current,
            "max": maximum,
            "pct": pct,
        }
        if self.wrapper and hasattr(self.wrapper, "reporter"):
            self.wrapper.reporter.add_data(
                self.village_id,
                data_type="village.farm_bag",
                data=json.dumps(payload),
            )

    def _log_farm_bag_block(self, state):
        now_ts = time.time()
        if now_ts - self._farm_bag_last_log < 300:
            return
        self._farm_bag_last_log = now_ts
        current = state.get("current", 0)
        maximum = state.get("max", 0)
        pct = (current / maximum * 100) if maximum else 0
        self.logger.info(
            "Farm bag limit reached for village %s: %d/%d (%.2f%%)",
            self.village_id,
            current,
            maximum,
            pct,
        )
        if self.wrapper and hasattr(self.wrapper, "reporter"):
            self.wrapper.reporter.report(
                self.village_id,
                "TWB_FARM_BAG_LIMIT",
                f"Farm bag limit reached: {current}/{maximum}",
            )

    def _refresh_farm_bag_state(self):
        if not self.wrapper or not self.village_id:
            return
        url = f"game.php?village={self.village_id}&screen=place"
        response = self.wrapper.get_url(url)
        if not response:
            return
        bag_state = Extractor.get_farm_bag_state(response)
        if not bag_state:
            return
        self.last_farm_bag_state = bag_state
        margin = max(0.0, min(1.0, self.farm_bag_limit_margin or 0.0))
        threshold = bag_state["max"] * (1 - margin)
        if bag_state["current"] < threshold:
            self._farm_bag_limit_reached = False
        else:
            self._farm_bag_limit_reached = True
        self._push_farm_bag_state()


class AttackCache:
    @staticmethod
    def get_cache(village_id):
        return FileManager.load_json_file(f"cache/attacks/{village_id}.json")

    @staticmethod
    def set_cache(village_id, entry):
        return FileManager.save_json_file(entry, f"cache/attacks/{village_id}.json")

    @staticmethod
    def cache_grab():
        output = {}

        for existing in FileManager.list_directory("cache/attacks", ends_with=".json"):
            output[existing.replace(".json", "")] = FileManager.load_json_file(f"cache/attacks/{existing}")
        return output
