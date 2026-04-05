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
from core.database import DatabaseManager
from game.farm_optimizer import FarmOptimizer
from game.attack_cache import AttackCache


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

    smart_farming = False
    smart_farming_priority = []
    min_farm_capacity = 0
    min_farm_units = 0

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
        # Statistics for the current run
        stats = {"sent": 0, "skipped_reservation": 0, "total_targets": 0}
        
        targets = self.targets[0: self.max_farms]
        stats["total_targets"] = len(targets)
        
        # Limits the amount of villages that are farmed from the current village
        for target in targets:
            if type(self.template) == list:
                f = False
                for template in self.template:
                    if template in ignored:
                        continue
                    out_res = self.send_farm(target, template)
                    if out_res == 1:
                        f = True
                        stats["sent"] += 1
                        break
                    elif out_res == -1:
                        ignored.append(template)
                    elif out_res == 0: # Reservation failed or other skip
                        stats["skipped_reservation"] += 1
                if not f:
                    continue
            else:
                out_res = self.send_farm(target, self.template)
                if out_res == 1:
                    stats["sent"] += 1
                elif out_res == 0:
                    stats["skipped_reservation"] += 1
                elif out_res == -1:
                    break

        # Advanced Logging: Overstacking detection
        if stats["total_targets"] > 0:
            rejection_rate = (stats["skipped_reservation"] / stats["total_targets"]) * 100
            self.logger.info(
                "Farming Loop Summary: Sent: %d, Reserved: %d (Rejection Rate: %.1f%%)",
                stats["sent"], stats["total_targets"] - stats["skipped_reservation"], rejection_rate
            )
            if rejection_rate > 75 and stats["total_targets"] > 5:
                self.logger.warning(
                    "HIGH OVERSTACKING DETECTED (%.1f%%). Consider increasing 'farm_radius' or decreasing troop allocation for village %s.",
                    rejection_rate, self.village_id
                )

    def get_smart_troops(self, template, max_loot_cap=None):
        """
        Calculates the troop composition based on loot capacity.
        max_loot_cap: optional upper limit to resources we expect to find
        """
        if not self.troopmanager or not hasattr(self.troopmanager, "carry_capacity"):
            return None

        # Calculate base target capacity from template
        template_capacity = sum(
            self.troopmanager.carry_capacity.get(unit, 0) * int(count)
            for unit, count in template.items()
        )
        
        # If we have a predicted cap, use it (but don't exceed what template allows)
        target_capacity = template_capacity
        if max_loot_cap is not None and max_loot_cap > 0:
            target_capacity = min(template_capacity, max_loot_cap)

        if target_capacity == 0:
            return None

        # Use dictionary comprehension for cleaner code
        available_troops = {unit: int(count_str) for unit, count_str in self.troopmanager.troops.items()}

        smart_troops = {}
        current_load = 0

        # Phase 1: Use template units first (prefer original template composition)
        for unit, count in template.items():
            if current_load >= target_capacity:
                break
            count = int(count)
            if unit in available_troops and available_troops[unit] > 0:
                capacity = self.troopmanager.carry_capacity.get(unit, 0)
                if capacity > 0:
                    # Limit template take by what's actually needed for target_capacity
                    needed = (target_capacity - current_load + capacity - 1) // capacity
                    take = min(available_troops[unit], count, needed)
                else:
                    take = min(available_troops[unit], count)
                
                if take > 0:
                    smart_troops[unit] = take
                    current_load += take * capacity
                    available_troops[unit] -= take

        # Phase 2: Fill remaining capacity gap with priority units
        if current_load < target_capacity:
            remaining_load = target_capacity - current_load
            priority_list = self.smart_farming_priority or ["light", "marcher", "heavy", "spear", "axe", "sword", "archer"]

            for unit in priority_list:
                if remaining_load <= 0:
                    break

                if unit in available_troops and available_troops[unit] > 0:
                    capacity = self.troopmanager.carry_capacity.get(unit, 0)
                    if capacity <= 0:
                        continue

                    # Optimized ceiling division: (a + b - 1) // b
                    needed = (remaining_load + capacity - 1) // capacity
                    take = min(available_troops[unit], needed)

                    if take > 0:
                        smart_troops[unit] = smart_troops.get(unit, 0) + take
                        added_load = take * capacity
                        current_load += added_load
                        remaining_load -= added_load
                        available_troops[unit] -= take

        # If we have no troops selected, return None (fail)
        if not smart_troops:
            self.logger.debug("Smart farming failed: no suitable troops available")
            return None

        # Check thresholds to prevent suicide attacks (e.g., sending 1 lonely axe)
        total_units = sum(smart_troops.values())
        if current_load < self.min_farm_capacity or total_units < self.min_farm_units:
            self.logger.debug(
                "Smart farming skipped: achieved capacity (%d < %d) or units (%d < %d) too low",
                current_load, self.min_farm_capacity, total_units, self.min_farm_units
            )
            return None

        # Log the smart farming result
        self.logger.debug(
            "Smart farming: target=%d, achieved=%d (%.1f%%), troops=%s",
            target_capacity, current_load, (current_load / target_capacity * 100) if target_capacity else 0, smart_troops
        )

        return smart_troops

    def send_farm(self, target, template):
        """
        Send a farming run
        """
        target, _ = target
        if self.farm_bag_limit_enabled and self._farm_bag_limit_reached:
            self.logger.debug("Skipping farm target because farm bag limit was reached earlier")
            return 0

        cache_entry = AttackCache.get_cache(target["id"])
        
        send_template = template.copy()
        
        requires_strict = False
        was_lost = False
        last_sent = None
        
        try:
            from core.database import DatabaseManager
            history = DatabaseManager.get_attack_history(target["id"], limit=1)
            if history and len(history) > 0:
                last_attack = history[0]
                for loss in last_attack.get("losses", []):
                    if loss.get("side") == "attacker" and loss.get("amount", 0) > 0:
                        was_lost = True
                        break
                if was_lost:
                    last_sent = last_attack.get("troops_sent")
                    if isinstance(last_sent, str):
                        import json
                        try:
                            last_sent = json.loads(last_sent)
                        except Exception:
                            last_sent = None
        except ImportError:
            pass
            
        if not was_lost and cache_entry and cache_entry.get("was_lost") and cache_entry.get("last_sent"):
            was_lost = True
            last_sent = cache_entry.get("last_sent")

        if was_lost and last_sent:
            scaled_template = {}
            for unit, count in last_sent.items():
                scaled_template[unit] = int(count) + int(template.get(unit, 1))
                
            for unit, count in template.items():
                if unit not in scaled_template:
                    scaled_template[unit] = int(count)
                    
            self.logger.info(
                "Previous attack to %s suffered losses. Scaling troops: %s -> %s",
                target["id"], last_sent, scaled_template
            )
            send_template = scaled_template
            requires_strict = True

        # --- ATOMIC RESERVATION OPTIMIZATION ---
        # Calculate target capacity for reservation
        target_capacity = sum(self.troopmanager.carry_capacity.get(u, 0) * int(c) for u, c in send_template.items())
        # Request roughly equal split of resources for the capacity
        req_res = target_capacity // 3
        
        success, res_w, res_s, res_i = DatabaseManager.reserve_farm_loot(
            target["id"], req_w=req_res, req_s=req_res, req_i=req_res, 
            min_threshold=self.min_farm_capacity
        )
        
        if not success:
            self.logger.debug("Skipping %s: Atomic reservation failed (not enough predicted loot)", target["id"])
            return 0
            
        total_reserved = res_w + res_s + res_i
        
        smart_template = None
        if self.smart_farming:
            # Use reserved resources as a target if it's lower than what template would fetch
            max_loot_target = total_reserved if total_reserved > 0 else 999999
            smart_template = self.get_smart_troops(send_template, max_loot_cap=max_loot_target)
            
        missing = False
        if smart_template:
            template = smart_template
            # Already checked reservation success above, so if we're here, it's worth the trip!
                
            if requires_strict and hasattr(self.troopmanager, "carry_capacity"):
                achieved_capacity = sum(self.troopmanager.carry_capacity.get(u, 0) * int(c) for u, c in smart_template.items())
                if achieved_capacity < target_capacity:
                    missing = f"Requires capacity {target_capacity}, but only {achieved_capacity} available."
                    self.logger.info("Farming scale-up failed for %s. %s", target["id"], missing)
        else:
            missing = self.enough_in_village(send_template)
            template = send_template

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
                # Night bonus check is now handled by FarmOptimizer.evaluate arrival calculation
                pass
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
        
        # LVA: Apply competition jitter
        jitter_pct = DatabaseManager.get_lva_jitter(vid)
        if jitter_pct > 0:
            self.logger.info("Competition detected for %s, applying %.1f%% jitter to delay", vid, jitter_pct * 100)
            min_time = int(min_time * (1 + jitter_pct))

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

        # --- FARM OPTIMIZER (CONTESTED DETECTION) ---
        optimizer = FarmOptimizer(
            self.village_id,
            default_wait=self.farm_default_wait,
            high_prio_wait=self.farm_high_prio_wait,
            low_prio_wait=self.farm_low_prio_wait,
        )
        
        # Calculate distance for travel time estimation
        distance = 0
        if vid in self.map.villages:
            distance = self.map.get_dist(self.map.villages[vid]["location"])
            
        # Get slowest unit from template for speed estimation
        slowest_unit = "light"
        from game.farm_optimizer import UNIT_SPEEDS
        
        active_template = self.template
        if isinstance(active_template, list) and len(active_template) > 0:
            active_template = active_template[0]
            
        if isinstance(active_template, dict):
             current_max = 0
             for u in active_template:
                 speed = UNIT_SPEEDS.get(u, 10.0)
                 if speed > current_max:
                     current_max = speed
                     slowest_unit = u

        recommended_wait, reason = optimizer.evaluate(vid, cache_entry["last_attack"], 
                                                     distance=distance, slowest_unit=slowest_unit)
        
        if cache_entry["last_attack"] + recommended_wait > int(time.time()):
            if reason == "morning_rush_wait":
                self.logger.info("Morning Rush: village %s scheduled for 08:00:01 (wait %d s)", 
                                 vid, recommended_wait)
            else:
                self.logger.debug(
                    "FarmOptimizer: skipping %s (reason=%s, recommended_wait=%d)",
                    vid, reason, recommended_wait
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
            "[Attack] %s -> %s duration %.1f h", self.village_id, vid, duration / 3600
        )

        confirm_data = {}
        for u in Extractor.attack_form(conf):
            k, v = u
            if k == "support":
                continue
            confirm_data[k] = v
        
        # Ensure we have at least SOME units in confirmation data
        # If no units are found, the confirm screen failed or was an error
        unit_found = False
        for k in confirm_data:
            if k in ["spear", "sword", "axe", "archer", "spy", "light", "marcher", "heavy", "ram", "catapult", "knight"]:
                if int(confirm_data[k]) > 0:
                    unit_found = True
                    break
        
        if not unit_found:
             self.logger.error("Attack confirmation failed for %s: No units found in confirmation form. Check session/CSRF.", vid)
             return False

        new_data = {"building": "main", "h": self.wrapper.last_h}
        confirm_data.update(new_data)
        if "x" not in confirm_data:
            confirm_data["x"] = x

        result = self.wrapper.get_api_action(
            village_id=self.village_id,
            action="popup_command",
            params={"screen": "place"},
            data=confirm_data,
        )
        
        # Verify if result actually contains a success indication
        if result and isinstance(result, dict):
            # In AJAX popup_command, successful attack usually has redirection or command info
            if "error" in str(result) or "dialog" in str(result):
                 if "error" in str(result):
                     self.logger.error("Attack to %s rejected by server: %s", vid, result.get("error"))
                     return False
        
        if not result:
            self.logger.error("Attack to %s failed: Empty response from server.", vid)
            return False

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
