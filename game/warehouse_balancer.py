"""Plan and execute resource transfers between owned villages."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from core.extractors import Extractor
from core.filemanager import FileManager


RESOURCE_TYPES = ("wood", "stone", "iron")


def _zero_resources() -> Dict[str, int]:
    return {res: 0 for res in RESOURCE_TYPES}


def _parse_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_coords(text: Optional[str]) -> Tuple[int, int]:
    if not text:
        return 0, 0
    match = re.search(r"\((\d+)\|(\d+)\)", text)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


@dataclass
class RequestEntry:
    resource: str
    amount: int
    priority: int
    source: str


@dataclass
class VillageState:
    village_id: str
    name: str
    coords: Tuple[int, int]
    storage: int
    resources: Dict[str, int]
    incoming: Dict[str, int]
    requests: List[RequestEntry]
    request_totals: Dict[str, int]
    under_attack: bool
    market_level: int
    merchants_avail: int
    merchants_total: int
    enabled: bool
    pending_needs: Dict[str, int] = field(default_factory=_zero_resources)
    planned_incoming: Dict[str, int] = field(default_factory=_zero_resources)
    planned_outgoing: Dict[str, int] = field(default_factory=_zero_resources)
    remaining_resources: Dict[str, int] = field(default_factory=_zero_resources)
    merchant_capacity: int = 0


@dataclass
class Shipment:
    source: VillageState
    destination: VillageState
    resources: Dict[str, int]

    def is_empty(self) -> bool:
        return not any(self.resources.get(res, 0) for res in RESOURCE_TYPES)


class ResourceCoordinator:
    """Implements the resource redistribution strategy described in the integration plan."""

    DEFAULTS = {
        "enabled": False,
        "mode": "requests_only",
        "needs_more_pct": 0.85,
        "built_out_pct": 0.25,
        "max_shipments_per_run": 25,
        "min_chunk": 1000,
        "transfer_cooldown_min": 10,
        "block_when_under_attack": True,
        "dry_run": True,
    }

    MERCHANT_CAPACITY = 1000

    def __init__(self, wrapper, config: Dict):
        self.wrapper = wrapper
        self.config = config or {}
        self.logger = logging.getLogger("ResourceCoordinator")
        self.settings = self._load_settings()
        self.ledger_path = "cache/transfer_ledger.json"
        self.ledger: Dict[str, float] = {}
        self.current_time = time.time()
        self.primary_village_id = self._detect_primary_village()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        if not self.settings["enabled"]:
            self.logger.debug("Resource balancer disabled; skipping")
            return

        self.current_time = time.time()

        if not self.primary_village_id:
            self.logger.debug("No village configured; skipping balancer run")
            return

        village_states = self._load_village_states()
        if not village_states:
            self.logger.debug("No managed village caches found; skipping")
            return

        self._augment_with_overviews(village_states)
        self._prepare_runtime_fields(village_states)
        self._load_ledger()

        shipments = self._plan_shipments(village_states)
        if not shipments:
            self.logger.debug("No shipments required in this run")
            return

        self._execute(shipments)

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _load_settings(self) -> Dict[str, object]:
        merged = dict(self.DEFAULTS)
        merged.update(self.config.get("balancer", {}))

        merged["enabled"] = bool(merged.get("enabled"))
        mode = str(merged.get("mode", "requests_only"))
        allowed_modes = {"requests_only", "balance_even"}
        if mode not in allowed_modes:
            self.logger.warning(
                "Unknown balancer mode '%s'; falling back to 'requests_only'", mode
            )
            mode = "requests_only"
        merged["mode"] = mode
        merged["needs_more_pct"] = float(merged.get("needs_more_pct", 0.85))
        merged["built_out_pct"] = float(merged.get("built_out_pct", 0.25))
        merged["max_shipments_per_run"] = max(0, _parse_int(merged.get("max_shipments_per_run")))
        merged["min_chunk"] = max(0, _parse_int(merged.get("min_chunk")))
        merged["transfer_cooldown_min"] = max(0, _parse_int(merged.get("transfer_cooldown_min")))
        merged["block_when_under_attack"] = bool(merged.get("block_when_under_attack", True))
        merged["dry_run"] = bool(merged.get("dry_run", True))
        return merged

    def _detect_primary_village(self) -> Optional[str]:
        villages = self.config.get("villages") or {}
        for vid in villages:
            return vid
        return None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_village_states(self) -> Dict[str, VillageState]:
        try:
            managed_files = FileManager.list_directory("cache/managed", ends_with=".json")
        except FileNotFoundError:
            return {}

        config_villages = self.config.get("villages") or {}
        states: Dict[str, VillageState] = {}

        for filename in managed_files:
            if not filename.endswith(".json"):
                continue
            village_id = filename[:-5]
            if config_villages and village_id not in config_villages:
                continue

            cache_entry = FileManager.load_json_file(f"cache/managed/{filename}")
            if not cache_entry:
                continue

            resources = {
                res: _parse_int(cache_entry.get("resources", {}).get(res, 0))
                for res in RESOURCE_TYPES
            }
            required = cache_entry.get("required_resources") or {}
            requests: List[RequestEntry] = []
            totals = _zero_resources()
            for source_name, res_map in required.items():
                if not isinstance(res_map, dict):
                    continue
                priority = self._source_priority(str(source_name))
                for res, value in res_map.items():
                    if res not in RESOURCE_TYPES:
                        continue
                    amount = _parse_int(value)
                    if amount <= 0:
                        continue
                    requests.append(RequestEntry(res, amount, priority, str(source_name)))
                    totals[res] += amount

            name = cache_entry.get("name") or f"Village {village_id}"
            coords = _parse_coords(name)
            building_levels = cache_entry.get("buidling_levels") or {}
            market_level = _parse_int(building_levels.get("market", 0))

            village_cfg = config_villages.get(village_id) or {}
            override = village_cfg.get("balancer_enabled")
            enabled = self.settings["enabled"] if override is None else bool(override)

            state = VillageState(
                village_id=village_id,
                name=name,
                coords=coords,
                storage=0,
                resources=resources,
                incoming=_zero_resources(),
                requests=sorted(requests, key=lambda r: (r.priority, -r.amount)),
                request_totals=totals,
                under_attack=bool(cache_entry.get("under_attack")),
                market_level=market_level,
                merchants_avail=0,
                merchants_total=0,
                enabled=enabled,
            )

            states[village_id] = state

        return states

    def _augment_with_overviews(self, states: Dict[str, VillageState]) -> None:
        production = self._fetch_overview("overview_villages&mode=prod")
        if production:
            for entry in Extractor.overview_production_data(production):
                vid = str(entry.get("id"))
                if vid not in states:
                    continue
                state = states[vid]
                state.storage = _parse_int(entry.get("storage"))
                coord = (entry.get("x", 0), entry.get("y", 0))
                if coord != (0, 0):
                    state.coords = (int(coord[0]), int(coord[1]))

        trader_own = self._fetch_overview("overview_villages&mode=trader&type=own")
        if trader_own:
            own_data = Extractor.overview_trader_data(trader_own, overview_type="own")
            for vid, entry in own_data.items():
                if vid not in states:
                    continue
                state = states[vid]
                state.merchants_avail = _parse_int(entry.get("merchants_avail"))
                state.merchants_total = _parse_int(entry.get("merchants_total"))

        trader_inc = self._fetch_overview("overview_villages&mode=trader&type=inc")
        if trader_inc:
            inc_data = Extractor.overview_trader_data(trader_inc, overview_type="inc")
            for vid, entry in inc_data.items():
                if vid not in states:
                    continue
                state = states[vid]
                state.incoming = {
                    "wood": _parse_int(entry.get("incoming_wood")),
                    "stone": _parse_int(entry.get("incoming_stone")),
                    "iron": _parse_int(entry.get("incoming_iron")),
                }

    def _prepare_runtime_fields(self, states: Dict[str, VillageState]) -> None:
        for state in states.values():
            state.remaining_resources = {
                res: max(0, state.resources.get(res, 0)) for res in RESOURCE_TYPES
            }
            state.planned_incoming = _zero_resources()
            state.planned_outgoing = _zero_resources()
            state.pending_needs = _zero_resources()
            state.merchant_capacity = max(0, state.merchants_avail * self.MERCHANT_CAPACITY)

    def _fetch_overview(self, path: str) -> Optional[str]:
        if not self.wrapper:
            return None
        try:
            url = f"game.php?village={self.primary_village_id}&screen={path}"
            response = self.wrapper.get_url(url)
            return response.text if response else None
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.debug("Failed to fetch %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    def _plan_shipments(self, states: Dict[str, VillageState]) -> List[Shipment]:
        shipments: Dict[Tuple[str, str], Shipment] = {}

        request_needs = self._build_request_needs(states)
        self._allocate_needs(request_needs, states, shipments, update_pending=True)

        if self.settings["mode"] == "balance_even":
            balance_needs = self._build_balance_needs(states)
            self._allocate_needs(balance_needs, states, shipments, update_pending=False)

        return [shipment for shipment in shipments.values() if not shipment.is_empty()]

    def _build_request_needs(self, states: Dict[str, VillageState]) -> List[Tuple[int, VillageState, str, int]]:
        needs: List[Tuple[int, VillageState, str, int]] = []
        for state in states.values():
            if not state.enabled:
                continue
            if self.settings["block_when_under_attack"] and state.under_attack:
                continue
            if not state.requests:
                continue

            available = {
                res: state.resources.get(res, 0) + state.incoming.get(res, 0)
                for res in RESOURCE_TYPES
            }

            for entry in state.requests:
                res = entry.resource
                demand = entry.amount
                if demand <= 0:
                    continue
                current_avail = available.get(res, 0)
                if current_avail >= demand:
                    available[res] = current_avail - demand
                    continue

                deficit = demand - current_avail
                available[res] = 0

                target_cap = self._target_cap(state)
                current_total = state.resources.get(res, 0) + state.incoming.get(res, 0) + state.planned_incoming.get(res, 0)
                if target_cap is not None:
                    deficit = min(deficit, max(0, target_cap - current_total))

                deficit = self._apply_chunk(deficit)
                if deficit <= 0:
                    continue

                state.pending_needs[res] += deficit
                needs.append((entry.priority, state, res, deficit))

        needs.sort(key=lambda item: (item[0], -item[3]))
        return needs

    def _build_balance_needs(self, states: Dict[str, VillageState]) -> List[Tuple[int, VillageState, str, int]]:
        needs: List[Tuple[int, VillageState, str, int]] = []
        for state in states.values():
            if not state.enabled or state.storage <= 0:
                continue
            if self.settings["block_when_under_attack"] and state.under_attack:
                continue
            target_cap = int(state.storage * self.settings["needs_more_pct"])
            for res in RESOURCE_TYPES:
                if state.pending_needs.get(res, 0) > 0:
                    continue
                current_level = state.resources.get(res, 0) + state.incoming.get(res, 0) + state.planned_incoming.get(res, 0)
                if current_level >= target_cap:
                    continue
                deficit = target_cap - current_level
                deficit = self._apply_chunk(deficit)
                if deficit <= 0:
                    continue
                needs.append((50, state, res, deficit))

        needs.sort(key=lambda item: (item[0], -item[3]))
        return needs

    def _allocate_needs(
        self,
        needs: Iterable[Tuple[int, VillageState, str, int]],
        states: Dict[str, VillageState],
        shipments: Dict[Tuple[str, str], Shipment],
        *,
        update_pending: bool,
    ) -> None:
        max_shipments = self.settings["max_shipments_per_run"]
        chunk = self.settings["min_chunk"]

        for _, destination, resource, required in needs:
            remaining = required
            if remaining <= 0:
                continue

            donors = self._candidate_sources(states, destination, resource)
            for source in donors:
                if remaining < chunk:
                    break

                exportable = self._exportable_amount(source, resource)
                if exportable < chunk:
                    continue

                send_amount = min(remaining, exportable, source.merchant_capacity)
                send_amount = self._apply_chunk(send_amount)
                if send_amount < chunk:
                    continue

                key = (source.village_id, destination.village_id)
                if key not in shipments:
                    if max_shipments and len(shipments) >= max_shipments:
                        self.logger.debug("Shipment cap reached (%d)", max_shipments)
                        return
                    if self._route_on_cooldown(key):
                        continue
                    shipments[key] = Shipment(
                        source=source,
                        destination=destination,
                        resources=_zero_resources(),
                    )

                shipments[key].resources[resource] += send_amount

                source.remaining_resources[resource] -= send_amount
                source.planned_outgoing[resource] += send_amount
                source.merchant_capacity = max(0, source.merchant_capacity - send_amount)
                destination.planned_incoming[resource] += send_amount
                if update_pending:
                    destination.pending_needs[resource] = max(0, destination.pending_needs[resource] - send_amount)

                remaining -= send_amount

            # leftover is carried into future runs

    def _candidate_sources(
        self,
        states: Dict[str, VillageState],
        destination: VillageState,
        resource: str,
    ) -> List[VillageState]:
        candidates: List[Tuple[float, VillageState]] = []
        for source in states.values():
            if source.village_id == destination.village_id:
                continue
            if not source.enabled:
                continue
            if self.settings["block_when_under_attack"] and source.under_attack:
                continue
            if source.market_level <= 0:
                continue
            if source.merchant_capacity < self.settings["min_chunk"]:
                continue
            if source.pending_needs.get(resource, 0) > 0:
                continue
            if self._exportable_amount(source, resource) < self.settings["min_chunk"]:
                continue
            distance = self._distance_squared(source.coords, destination.coords)
            candidates.append((distance, source))

        candidates.sort(key=lambda item: item[0])
        return [source for _, source in candidates]

    # ------------------------------------------------------------------
    # Calculations & guards
    # ------------------------------------------------------------------
    def _exportable_amount(self, state: VillageState, resource: str) -> int:
        reserve_storage = int(state.storage * self.settings["built_out_pct"]) if state.storage else 0
        reserve_requests = state.request_totals.get(resource, 0)
        reserve = max(reserve_storage, reserve_requests)
        available = state.remaining_resources.get(resource, 0) - reserve
        return max(0, available)

    def _target_cap(self, state: VillageState) -> Optional[int]:
        if state.storage <= 0:
            return None
        return int(state.storage * self.settings["needs_more_pct"])

    def _apply_chunk(self, amount: int) -> int:
        chunk = self.settings["min_chunk"]
        if chunk <= 0:
            return max(0, amount)
        return max(0, (amount // chunk) * chunk)

    @staticmethod
    def _distance_squared(a: Tuple[int, int], b: Tuple[int, int]) -> float:
        ax, ay = a
        bx, by = b
        return (ax - bx) ** 2 + (ay - by) ** 2

    # ------------------------------------------------------------------
    # Ledger management
    # ------------------------------------------------------------------
    def _load_ledger(self) -> None:
        data = FileManager.load_json_file(self.ledger_path)
        if not data:
            self.ledger = {}
            return
        cooldown = self.settings["transfer_cooldown_min"] * 60
        now = self.current_time
        self.ledger = {
            key: ts
            for key, ts in data.items()
            if isinstance(ts, (int, float)) and (cooldown <= 0 or now - ts < cooldown)
        }

    def _route_on_cooldown(self, key: Tuple[str, str]) -> bool:
        signature = f"{key[0]}->{key[1]}"
        if signature not in self.ledger:
            return False
        cooldown = self.settings["transfer_cooldown_min"] * 60
        if cooldown <= 0:
            return False
        return self.current_time - self.ledger.get(signature, 0) < cooldown

    def _record_routes(self, shipments: List[Shipment]) -> None:
        if not shipments:
            return
        now = self.current_time
        for shipment in shipments:
            signature = f"{shipment.source.village_id}->{shipment.destination.village_id}"
            self.ledger[signature] = now
        FileManager.save_json_file(self.ledger, self.ledger_path)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _execute(self, shipments: List[Shipment]) -> None:
        dry_run = self.settings["dry_run"]
        reporter = getattr(self.wrapper, "reporter", None) if self.wrapper else None

        successful: List[Shipment] = []

        for shipment in shipments:
            if shipment.is_empty():
                continue

            resources = {res: shipment.resources.get(res, 0) for res in RESOURCE_TYPES}
            payload_desc = (
                f"{shipment.source.village_id}->{shipment.destination.village_id} "
                f"wood={resources['wood']} stone={resources['stone']} iron={resources['iron']}"
            )

            if dry_run:
                self.logger.info("[Dry-Run] Planned shipment %s", payload_desc)
                if reporter and hasattr(reporter, "report"):
                    reporter.report(shipment.source.village_id, "TWB_BALANCER", f"DRY: {payload_desc}")
                continue

            if not self.wrapper:
                self.logger.warning("No wrapper available to send shipment %s", payload_desc)
                continue

            response = self.wrapper.get_api_action(
                village_id=shipment.source.village_id,
                action="map_send",
                params={"screen": "market"},
                data={
                    "target_id": shipment.destination.village_id,
                    "wood": resources["wood"],
                    "stone": resources["stone"],
                    "iron": resources["iron"],
                },
            )

            success = bool(response)
            if success:
                self.logger.info("Sent shipment %s", payload_desc)
                successful.append(shipment)
            else:
                self.logger.warning("Failed to send shipment %s", payload_desc)

            if reporter and hasattr(reporter, "report"):
                status = "SENT" if success else "FAILED"
                reporter.report(shipment.source.village_id, "TWB_BALANCER", f"{status}: {payload_desc}")

        if not dry_run and successful:
            self._record_routes(successful)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _source_priority(source: str) -> int:
        if source == "building":
            return 0
        if source == "snob":
            return 1
        if source.startswith("recruitment"):
            return 2
        return 5


__all__ = ["ResourceCoordinator"]
