"""Reusable monitor service for scripts and GUI."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from alerts.base import AlertManager
from alerts.email import EmailAlertSink
from alerts.formatter import format_signal_alert
from alerts.telegram import TelegramAlertSink
from config.settings import Settings, format_timeframe_label
from data.kraken_rest import KrakenRestClient
from data.models import BookSnapshot, Candle, Trade
from features.footprint import CandleFootprint, compute_candle_footprints
from features.structure import StructureZone, detect_structure_zones
from features.timeseries import CandleFeaturePoint, FlowPriceImbalance, compute_candle_feature_series, extract_imbalance_markers
from signals.composite import MonitorSnapshot, analyze_market_state
from storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class MonitorBundle:
    symbol: str
    interval_minutes: int
    candles: list[Candle]
    trades: list[Trade]
    book_snapshot: BookSnapshot
    analysis: MonitorSnapshot
    candle_feature_series: list[CandleFeaturePoint]
    candle_footprints: list[CandleFootprint]
    imbalance_markers: list[FlowPriceImbalance]
    structure_zones: list[StructureZone]

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval_minutes": self.interval_minutes,
            "analysis": self.analysis.as_dict(),
            "candle_feature_series": [point.as_dict() for point in self.candle_feature_series],
            "candle_footprints": [
                {
                    "open_time": footprint.candle.open_time.isoformat(),
                    "buy_volume": str(footprint.buy_volume),
                    "sell_volume": str(footprint.sell_volume),
                    "total_volume": str(footprint.total_volume),
                    "normalized_delta": footprint.normalized_delta,
                    "trade_count": footprint.trade_count,
                    "price_increment": str(footprint.price_increment),
                    "price_levels": [
                        {
                            "lower_price": str(level.lower_price),
                            "upper_price": str(level.upper_price),
                            "buy_volume": str(level.buy_volume),
                            "sell_volume": str(level.sell_volume),
                            "total_volume": str(level.total_volume),
                            "normalized_delta": level.normalized_delta,
                        }
                        for level in footprint.price_levels
                    ],
                }
                for footprint in self.candle_footprints
            ],
            "imbalance_markers": [marker.as_dict() for marker in self.imbalance_markers],
            "structure_zones": [zone.as_dict() for zone in self.structure_zones],
        }


def build_alert_manager(settings: Settings) -> AlertManager:
    sinks = []
    if settings.telegram.enabled:
        sinks.append(TelegramAlertSink(settings.telegram))
    if settings.email.enabled:
        sinks.append(EmailAlertSink(settings.email))
    return AlertManager(sinks)


def _persist_and_alert_signal(
    snapshot: MonitorSnapshot,
    store: SQLiteStore,
    alert_manager: AlertManager,
    settings: Settings,
) -> None:
    if snapshot.signal is None:
        return

    latest = store.latest_signal_timestamp(
        snapshot.signal.symbol,
        snapshot.signal.timeframe,
        snapshot.signal.setup_name,
    )
    is_new_signal = latest is None or snapshot.signal.detected_at > latest
    if settings.monitor.persist_signals and is_new_signal:
        store.insert_signal(snapshot.signal)
    if is_new_signal:
        alert_manager.send(format_signal_alert(snapshot.signal))


def collect_market_bundles(
    settings: Settings,
    store: SQLiteStore,
    alert_manager: AlertManager,
    *,
    symbols: list[str] | None = None,
    intervals: list[int] | None = None,
) -> list[MonitorBundle]:
    selected_symbols = symbols or settings.monitor.symbols
    selected_intervals = intervals or settings.monitor.intervals

    bundles: list[MonitorBundle] = []
    with KrakenRestClient(settings.rest) as client:
        pairs = client.get_asset_pairs()
        store.upsert_asset_pairs(pairs)

        for symbol in selected_symbols:
            trades = client.get_trades(symbol, limit=settings.rest.trade_limit)
            book = client.get_depth(symbol, count=settings.rest.depth_levels)
            store.insert_trades(trades)
            store.insert_book_snapshot(book)

            for interval in selected_intervals:
                candles = client.get_ohlc(symbol, interval)
                if len(candles) < 2:
                    continue
                store.upsert_candles(candles)
                series_trades = store.load_trades(
                    symbol,
                    start_time=candles[0].open_time,
                    end_time=candles[-1].close_time,
                )
                if not series_trades:
                    series_trades = trades
                analysis = analyze_market_state(
                    symbol=symbol,
                    timeframe=format_timeframe_label(interval),
                    candles=candles,
                    trades=trades,
                    book_snapshot=book,
                    settings=settings,
                )
                _persist_and_alert_signal(analysis, store, alert_manager, settings)
                series = compute_candle_feature_series(candles, series_trades, settings.features)
                footprints = compute_candle_footprints(
                    candles,
                    series_trades,
                    levels_per_candle=settings.features.footprint_levels_per_candle,
                    min_price_increment=Decimal(str(settings.features.footprint_min_price_increment)),
                )
                structure_zones = detect_structure_zones(candles, settings.features)
                bundles.append(
                    MonitorBundle(
                        symbol=symbol,
                        interval_minutes=interval,
                        candles=candles,
                        trades=trades,
                        book_snapshot=book,
                        analysis=analysis,
                        candle_feature_series=series,
                        candle_footprints=footprints,
                        imbalance_markers=extract_imbalance_markers(series),
                        structure_zones=structure_zones,
                    )
                )
    return bundles
