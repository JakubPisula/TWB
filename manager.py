import json
import logging
import os
import sys

from game.attack import AttackCache
from game.warehouse_balancer import ResourceCoordinator


class VillageManager:
    @staticmethod
    def farm_manager(verbose=False, clean_reports=False):
        logger = logging.getLogger("FarmManager")
        with open("config.json", "r") as f:
            config = json.load(f)

        if verbose:
            logger.info("Villages: %d", len(config["villages"]))
        attacks = AttackCache.cache_grab()
        # --- PERFORMANCE (POINT 3) ---
        # Report reading is no longer needed, stats are in AttackCache
        # reports = ReportCache.cache_grab()

        # if verbose:
        #     logger.info("Reports: %d", len(reports))
        # --- END PERFORMANCE ---

        logger.info("Farms: %d", len(attacks))

        t = {"wood": 0, "iron": 0, "stone": 0}

        for farm in attacks:
            data = attacks[farm]

            # --- PERFORMANCE (POINT 3) ---
            # Read pre-calculated stats directly from the cache entry
            loot = data.get("total_loot", {"wood": 0, "iron": 0, "stone": 0})
            num_attack = data.get("attack_count", 0)
            total_loss_count = data.get("total_losses", 0)
            total_sent_count = data.get("total_sent", 0)

            for r in loot:
                t[r] = t[r] + int(loot[r])

            percentage_lost = 0
            if total_sent_count > 0:
                percentage_lost = total_loss_count / total_sent_count * 100
            # --- END PERFORMANCE ---

            perf = ""
            if data.get("high_profile"):
                perf = "High Profile "
            if data.get("low_profile"):
                perf = "Low Profile "

            if verbose:
                logger.info(
                    "%sFarm village %s attacked %d times - Total loot: %s - Total units lost: %d (%.2f)",
                    perf, farm, num_attack, str(loot), total_loss_count, percentage_lost
                )

            # --- PERFORMANCE (POINT 3) ---
            # All profiling logic has been moved to ReportManager.attack_report
            # This function is now read-only.
            # --- END PERFORMANCE ---

        if verbose:
            logger.info("Total loot: %s" % t)

        if clean_reports:
            list_of_files = sorted(["./cache/reports/" + f for f in os.listdir("./cache/reports/")],
                                   key=os.path.getctime)

            logger.info(f"Found {len(list_of_files)} files")

            while len(list_of_files) > clean_reports:
                oldest_file = list_of_files.pop(0)
                logger.info(f"Delete old report ({oldest_file})")
                os.remove(os.path.abspath(oldest_file))

    @staticmethod
    def resource_balancer(wrapper, config):
        coordinator = ResourceCoordinator(wrapper=wrapper, config=config)
        try:
            coordinator.run()
        except Exception as exc:  # pragma: no cover - defensive guard
            logging.getLogger("ResourceCoordinator").exception("Resource balancer failed: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout)
    VillageManager.farm_manager(verbose=True)
