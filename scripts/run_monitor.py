"""Run the end-to-end backend monitor loop."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
import time

from alerts.base import AlertManager
from alerts.email import EmailAlertSink
from alerts.formatter import format_signal_alert
from alerts.telegram import TelegramAlertSink
from config.settings import Settings
from data.kraken_rest import KrakenRestClient
from signals.composite import analyze_market_state
from storage.sqlite_store import SQLiteStore


LOGGER = logging.getLogger(__name__)


def build_alert_manager(settings: Settings) -> AlertManager:
    sinks = []
    if settings.telegram.enabled:
        sinks.append(TelegramAlertSink(settings.telegram))
    if settings.email.enabled:
        sinks.append(EmailAlertSink(settings.email))
    return AlertManager(sinks)


def run_iteration(settings: Settings, store: SQLiteStore, alert_manager: AlertManager) -> list[dict[str, object]]:
    outputs: list[dict[str, object]] = []
    with KrakenRestClient(settings.rest) as client:
        pairs = client.get_asset_pairs()
        store.upsert_asset_pairs(pairs)
        for symbol in settings.monitor.symbols:
            trades = client.get_trades(symbol, limit=settings.rest.trade_limit)
            book = client.get_depth(symbol, count=settings.rest.depth_levels)
            store.insert_trades(trades)
            store.insert_book_snapshot(book)
            for interval in settings.monitor.intervals:
                candles = client.get_ohlc(symbol, interval)
                if len(candles) < 2:
                    continue
                store.upsert_candles(candles)
                snapshot = analyze_market_state(
                    symbol=symbol,
                    timeframe=f"{interval}m",
                    candles=candles,
                    trades=trades,
                    book_snapshot=book,
                    settings=settings,
                )
                payload = snapshot.as_dict()
                outputs.append(payload)
                if snapshot.signal:
                    if settings.monitor.persist_signals:
                        store.insert_signal(snapshot.signal)
                    alert_manager.send(format_signal_alert(snapshot.signal))
    return outputs


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
