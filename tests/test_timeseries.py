from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from config.settings import FeatureSettings
from data.models import Candle, Trade
from features.timeseries import compute_candle_feature_series, extract_imbalance_markers


def _candle(index: int, open_: str, close: str) -> Candle:
    open_time = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=index)
    high = str(max(Decimal(open_), Decimal(close)) + Decimal("1"))
    low = str(min(Decimal(open_), Decimal(close)) - Decimal("1"))
    return Candle(
        symbol="BTC/USD",
        interval_minutes=60,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        vwap=Decimal(close),
        volume=Decimal("100"),
        trade_count=10,
    )


def _trade(hours: int, minutes: int, side: str, price: str, volume: str) -> Trade:
    return Trade(
        symbol="BTC/USD",
        price=Decimal(price),
        volume=Decimal(volume),
        side=side,
        order_type="limit",
        timestamp=datetime(2024, 1, 1, hours, minutes, tzinfo=UTC),
    )


def test_compute_candle_feature_series_flags_buying_and_selling_mismatches() -> None:
    candles = [
        _candle(0, "100", "99"),
        _candle(1, "99", "100"),
    ]
    trades = [
        _trade(0, 5, "buy", "100.2", "4"),
        _trade(0, 10, "buy", "100.1", "3"),
        _trade(0, 15, "sell", "99.9", "1"),
        _trade(1, 5, "sell", "98.8", "5"),
        _trade(1, 12, "sell", "98.7", "4"),
        _trade(1, 16, "buy", "99.4", "1"),
    ]
    settings = FeatureSettings(
        imbalance_strength_threshold=0.6,
        imbalance_blocked_threshold=0.4,
        imbalance_min_trade_count=1,
    )

    series = compute_candle_feature_series(candles, trades, settings)
    markers = extract_imbalance_markers(series)

    assert [point.imbalance_label for point in series] == ["Blocked buying", "Blocked selling"]
    assert [marker.label for marker in markers] == ["Blocked buying", "Blocked selling"]
