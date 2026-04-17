"""Serialization helpers for the browser dashboard API."""

from __future__ import annotations

from datetime import UTC, datetime

from config.settings import Settings, format_timeframe_label
from services.monitor import MonitorBundle


INDICATOR_OPTIONS: tuple[tuple[str, str], ...] = (
    ("delta", "Delta"),
    ("bid_ask", "Bid / Ask"),
)


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((alpha * value) + ((1 - alpha) * ema_values[-1]))
    return ema_values


def _serialize_candles(bundle: MonitorBundle) -> list[dict[str, object]]:
    return [
        {
            "open_time": candle.open_time.isoformat(),
            "close_time": candle.close_time.isoformat(),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
            "trade_count": candle.trade_count,
        }
        for candle in bundle.candles
    ]


def _serialize_summary(bundle: MonitorBundle) -> dict[str, object]:
    closes = [float(candle.close) for candle in bundle.candles]
    opens = [float(candle.open) for candle in bundle.candles]
    highs = [float(candle.high) for candle in bundle.candles]
    lows = [float(candle.low) for candle in bundle.candles]
    ema_12 = _ema(closes, 12)
    ema_144 = _ema(closes, 144)
    ema_169 = _ema(closes, 169)
    ema_238 = _ema(closes, 238)
    ema_338 = _ema(closes, 338)
    previous_close = closes[-2] if len(closes) > 1 else closes[-1]
    price_change = closes[-1] - previous_close
    percent_change = (price_change / previous_close * 100) if previous_close else 0.0
    return {
        "open": opens[-1],
        "high": highs[-1],
        "low": lows[-1],
        "close": closes[-1],
        "price_change": price_change,
        "percent_change": percent_change,
        "ema_12": ema_12[-1],
        "ema_144": ema_144[-1],
        "ema_169": ema_169[-1],
        "ema_238": ema_238[-1],
        "ema_338": ema_338[-1],
    }


def _serialize_watchlist_entry(bundle: MonitorBundle) -> dict[str, object]:
    closes = [float(candle.close) for candle in bundle.candles]
    last_close = closes[-1]
    previous_close = closes[-2] if len(closes) > 1 else last_close
    change = last_close - previous_close
    percent = (change / previous_close * 100) if previous_close else 0.0
    signal = bundle.analysis.signal
    return {
        "symbol": bundle.symbol,
        "display_symbol": bundle.symbol.replace("/", ""),
        "last": last_close,
        "change": change,
        "percent": percent,
        "setup_name": signal.setup_name if signal is not None else "Monitoring",
    }


def _serialize_bundle(bundle: MonitorBundle) -> dict[str, object]:
    return {
        "symbol": bundle.symbol,
        "interval_minutes": bundle.interval_minutes,
        "interval_label": format_timeframe_label(bundle.interval_minutes),
        "candles": _serialize_candles(bundle),
        "summary": _serialize_summary(bundle),
        "analysis": bundle.analysis.as_dict(),
        "candle_feature_series": [point.as_dict() for point in bundle.candle_feature_series],
        "candle_footprints": [
            {
                "open_time": footprint.candle.open_time.isoformat(),
                "buy_volume": float(footprint.buy_volume),
                "sell_volume": float(footprint.sell_volume),
                "total_volume": float(footprint.total_volume),
                "normalized_delta": footprint.normalized_delta,
                "trade_count": footprint.trade_count,
                "price_increment": float(footprint.price_increment),
                "price_levels": [
                    {
                        "lower_price": float(level.lower_price),
                        "upper_price": float(level.upper_price),
                        "buy_volume": float(level.buy_volume),
                        "sell_volume": float(level.sell_volume),
                        "total_volume": float(level.total_volume),
                        "normalized_delta": level.normalized_delta,
                    }
                    for level in footprint.price_levels
                ],
            }
            for footprint in bundle.candle_footprints
        ],
        "imbalance_markers": [marker.as_dict() for marker in bundle.imbalance_markers],
        "watchlist_entry": _serialize_watchlist_entry(bundle),
    }


def build_dashboard_payload(
    bundles: list[MonitorBundle],
    settings: Settings,
    *,
    selected_symbol: str,
    selected_interval: int,
) -> dict[str, object]:
    bundle_map = {bundle.symbol: bundle for bundle in bundles}
    if selected_symbol not in bundle_map:
        selected_symbol = bundles[0].symbol

    watchlist = [
        _serialize_watchlist_entry(bundle_map[symbol])
        for symbol in settings.monitor.symbols
        if symbol in bundle_map
    ]

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "selected_symbol": selected_symbol,
        "selected_interval": selected_interval,
        "symbols": settings.monitor.symbols,
        "intervals": settings.monitor.intervals,
        "indicator_options": [{"key": key, "label": label} for key, label in INDICATOR_OPTIONS],
        "bundles": {symbol: _serialize_bundle(bundle) for symbol, bundle in bundle_map.items()},
        "watchlist": watchlist,
    }
