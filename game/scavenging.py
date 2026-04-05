import logging
import time
import random
from math import ceil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

@dataclass
class ScavengeLevel:
    level_id: int
    capacity: int          # maks. surowce do zebrania
    duration_seconds: int  # czas podróży w sekundach
    is_locked: bool
    is_running: bool

@dataclass
class ScavengeAssignment:
    level_id: int
    units: dict  # {"sword": N, "spear": N, ...}

class ScavengingUnavailableError(Exception):
    """Raised when scavenging is not available for the village."""
    pass

class ScavengingManager:
    """
    Zarządza automatycznym zbieractwem dla jednej wioski.
    Pobiera dane z gry przez HTTP (ciasteczka z core/), parsuje
    dostępne poziomy zbieractwa i optymalnie rozdziela jednostki
    defensywne pomiędzy poziomami, maksymalizując surowce/h.
    """

    UNIT_CARRY = {
        "spear":   25,
        "sword":   15,
        "axe":     10,
        "archer":  10,
        "light":   80,   # LK — zarezerwowana, nie używana
        "marcher": 50,  # zarezerwowana, nie używana
        "heavy":   50,
        "ram":      0,
        "catapult": 0,
        "knight":  100,
        "snob":     0,
    }

    def __init__(self, village_id: int, config: dict, wrapper):
        """
        Initialize ScavengingManager.
        
        :param village_id: ID wioski (int)
        :param config: słownik village_template z config.json
        :param wrapper: instancja WebWrapper z core/request.py
        """
        self.village_id = village_id
        self.config = config
        self.wrapper = wrapper
        self.logger = logging.getLogger(f"Scavenging:{village_id}")
        self.last_run = 0

    def fetch_scavenge_page(self) -> BeautifulSoup:
        """
        Pobiera stronę: https://{server}/game.php?village={village_id}&screen=place&mode=scavenge
        Rzuca ScavengingUnavailableError jeśli zakładka jest niedostępna
        """
        url = f"game.php?village={self.village_id}&screen=place&mode=scavenge"
        response = self.wrapper.get_url(url)
        if not response or "mode=scavenge" not in response.url:
            raise ScavengingUnavailableError("Scavenging mode not available or redirect occurred")
        
        soup = BeautifulSoup(response.text, "html.parser")
        # Check if scavenging is actually there
        if not soup.select_one(".scavenge-option"):
            raise ScavengingUnavailableError("No scavenge options found on page")
            
        return soup

    def parse_available_units(self, soup: BeautifulSoup) -> Dict[str, int]:
        """
        Wyciąga aktualnie dostępne (nie w drodze) jednostki wioski ze strony zbieractwa
        Pomija jednostki z gather_reserve_for_farm (default 100% dla LK, marcher)
        Pomija jednostki nieobecne w gather_unit_priority
        """
        units = {}
        priority_units = self.config.get("gather_unit_priority", ["sword", "spear", "axe"])
        reserve_cfg = self.config.get("gather_reserve_for_farm", {"light": 1.0, "marcher": 1.0})

        # Units are usually in a container with class "units-entry-all" or similar
        # But Tribal Wars often has them in a script or specific spans
        unit_containers = soup.select(".units-entry-all")
        for container in unit_containers:
            unit_name = container.get("data-unit")
            if not unit_name:
                continue
            
            count_text = container.text.strip("() ")
            try:
                count = int(count_text)
            except ValueError:
                count = 0
            
            if count <= 0:
                continue

            # Check priority and reserves
            if unit_name not in priority_units:
                continue
            
            reserve_ratio = reserve_cfg.get(unit_name, 0.0)
            available_after_reserve = floor_count = int(count * (1.0 - reserve_ratio))
            
            if available_after_reserve > 0:
                units[unit_name] = available_after_reserve

        self.logger.debug(f"Available units for scavenging: {units}")
        return units

    def parse_scavenge_levels(self, soup: BeautifulSoup) -> List[ScavengeLevel]:
        """
        Wyciąga dostępne poziomy zbieractwa z HTML
        Filtruje do poziomów z gather_levels (domyślnie [1,2,3])
        Pomija poziomy, które już trwają (is_running=True)
        """
        levels = []
        enabled_levels = self.config.get("gather_levels", [1, 2, 3])
        
        options = soup.select(".scavenge-option")
        for opt in options:
            try:
                # Identification of level
                # Usually there's a button or a hidden input with option_id
                btn = opt.select_one(".free_send_button")
                if not btn:
                    # Maybe it's locked or running
                    # Check for lock icon or timer
                    is_locked = bool(opt.select_one(".lock"))
                    is_running = bool(opt.select_one(".timer"))
                    
                    # If it's running, we can still get the ID from data-option-id if present
                    # or from the order of elements
                    level_id_match = re.search(r'ScavengeWidgets\.sendSquads\((\d+)', opt.decode_contents())
                    if level_id_match:
                        level_id = int(level_id_match.group(1))
                    else:
                        # Fallback to a less reliable way if needed, but usually Tribal Wars 
                        # has structured data here
                        continue
                else:
                    level_id = int(btn.get("data-option-id", 0))
                    is_locked = False
                    is_running = False

                if level_id not in enabled_levels:
                    continue
                
                if is_locked or is_running:
                    continue

                # Capacity and duration are often in the description or data attributes
                # If not easily available, we might need to parse them from the text
                # "Zdolność łupu: 1000" etc.
                capacity = 0
                cap_el = opt.select_one(".status-specific")
                if cap_el:
                    cap_text = cap_el.text
                    cap_match = re.search(r'(\d+)', cap_text.replace(".", ""))
                    if cap_match:
                        capacity = int(cap_match.group(1))

                # Duration is harder to get without units selected, but sometimes it's there
                duration = 0 # Not strictly needed for the greedy split algorithm if we use capacity

                levels.append(ScavengeLevel(
                    level_id=level_id,
                    capacity=capacity,
                    duration_seconds=duration,
                    is_locked=is_locked,
                    is_running=is_running
                ))
            except Exception as e:
                self.logger.warning(f"Error parsing scavenge option: {e}")
                continue
                
        return levels

    def calculate_optimal_split(self, units: Dict[str, int], levels: List[ScavengeLevel]) -> List[ScavengeAssignment]:
        """
        Algorytm optymalnego podziału wojsk.
        1. Policz łączną nośność dostępnych jednostek.
        2. Posortuj poziomy malejąco po capacity.
        3. Przydziel jednostki zachłannie.
        """
        if not units or not levels:
            return []

        total_carry = sum(count * self.UNIT_CARRY.get(u, 0) for u, count in units.items())
        if total_carry == 0:
            return []

        # Sort levels descending by capacity (higher levels first)
        sorted_levels = sorted(levels, key=lambda x: x.capacity, reverse=True)
        
        min_fill_ratio = self.config.get("gather_min_fill_ratio", 0.85)
        assignments = []
        
        remaining_units = {k: v for k, v in units.items()}
        
        # We want to fill levels to their capacity if possible, 
        # but also distribute what we have.
        # If we have one level, we send everything there (if >= min_fill_ratio).
        # If we have multiple, we fill the highest one first.

        for level in sorted_levels:
            current_remaining_carry = sum(count * self.UNIT_CARRY.get(u, 0) for u, count in remaining_units.items())
            if current_remaining_carry == 0:
                break
                
            if current_remaining_carry < level.capacity * min_fill_ratio:
                # This level cannot be filled to minimum, skip it
                continue
            
            # How many units to send to fill this level up to its capacity?
            # If we have more than enough, we take only what's needed for 100% capacity.
            # If we have less than 100% but more than min_fill_ratio%, we take all.
            
            target_carry = level.capacity
            if current_remaining_carry <= target_carry:
                # Take all remaining
                assignments.append(ScavengeAssignment(level_id=level.level_id, units={k: v for k, v in remaining_units.items() if v > 0}))
                for k in remaining_units: remaining_units[k] = 0
            else:
                # Take proportional amount to reach 100% capacity
                ratio = target_carry / current_remaining_carry
                level_units = {}
                for u, count in remaining_units.items():
                    to_send = int(count * ratio)
                    if to_send > 0:
                        level_units[u] = to_send
                        remaining_units[u] -= to_send
                if level_units:
                    assignments.append(ScavengeAssignment(level_id=level.level_id, units=level_units))

        return assignments

    def send_scavenge(self, assignment: ScavengeAssignment) -> bool:
        """
        Wysyła POST do gry dla danego poziomu zbieractwa.
        """
        # Tribal Wars uses a specific API for sending squads
        # Payload: {"squad_requests[0][village_id]": ..., "squad_requests[0][option_id]": ..., ...}
        
        payload = {
            "squad_requests[0][village_id]": self.village_id,
            "squad_requests[0][option_id]": str(assignment.level_id),
            "squad_requests[0][use_premium]": "false",
            "h": self.wrapper.last_h
        }
        
        total_carry = 0
        for unit, count in assignment.units.items():
            payload[f"squad_requests[0][candidate_squad][unit_counts][{unit}]"] = str(count)
            total_carry += count * self.UNIT_CARRY.get(unit, 0)
            
        payload["squad_requests[0][candidate_squad][carry_max]"] = str(total_carry)
        
        self.logger.info(f"Sending scavenging level {assignment.level_id} with units: {assignment.units}")
        
        # Use post_api_data or post_url? GatherMixin uses get_api_action (which is a POST)
        result = self.wrapper.post_api_data(
            village_id=self.village_id,
            action="send_squads",
            params={"screen": "scavenge_api"},
            data=payload
        )
        
        if result and (result == True or (isinstance(result, dict) and result.get("success"))):
            return True
        
        self.logger.error(f"Failed to send scavenging for level {assignment.level_id}: {result}")
        return False

    def run(self) -> None:
        """
        Główna pętla wywoływana przez schedulera bota.
        """
        if not self.config.get("gather_enabled", False):
            return

        cooldown_mins = self.config.get("gather_cooldown_minutes", 5)
        if time.time() - self.last_run < cooldown_mins * 60:
            return

        self.last_run = time.time()

        try:
            soup = self.fetch_scavenge_page()
            units = self.parse_available_units(soup)
            if not units:
                self.logger.debug("No units available for scavenging")
                return

            levels = self.parse_scavenge_levels(soup)
            if not levels:
                self.logger.debug("No scavenging levels available")
                return

            assignments = self.calculate_optimal_split(units, levels)
            for assign in assignments:
                success = self.send_scavenge(assign)
                if success:
                    # Small delay between sending different levels
                    time.sleep(random.uniform(1.0, 3.0))
                
        except ScavengingUnavailableError as e:
            self.logger.warning(f"Scavenging unavailable: {e}")
        except Exception as e:
            self.logger.exception(f"Unexpected error in ScavengingManager: {e}")

import re
