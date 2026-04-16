"""Run the end-to-end backend monitor loop."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
import time

from alerts.base import AlertManager
from config.settings import Settings
from services.monitor import build_alert_manager, collect_market_bundles
from storage.sqlite_store import SQLiteStore


LOGGER = logging.getLogger(__name__)


def run_iteration(settings: Settings, store: SQLiteStore, alert_manager: AlertManager) -> list[dict[str, object]]:
    bundles = collect_market_bundles(settings, store, alert_manager)
    return [bundle.as_dict() for bundle in bundles]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--poll-seconds", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    if args.symbols:
        settings.monitor.symbols = args.symbols
    if args.poll_seconds is not None:
        settings.monitor.poll_seconds = args.poll_seconds

    store = SQLiteStore(settings.storage.sqlite_path)
    alert_manager = build_alert_manager(settings)

    for iteration in range(args.iterations):
        LOGGER.info("Monitor iteration %s started", iteration + 1)
        outputs = run_iteration(settings, store, alert_manager)
        print(json.dumps({"ran_at": datetime.now(tz=UTC).isoformat(), "results": outputs}, indent=2))
        LOGGER.info("Monitor iteration %s finished with %s results", iteration + 1, len(outputs))
        if iteration + 1 < args.iterations:
            time.sleep(settings.monitor.poll_seconds)


if __name__ == "__main__":
    main()
