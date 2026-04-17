from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from config.settings import FeatureSettings
from data.models import Candle
from features.structure import detect_fair_value_gaps, detect_order_blocks, detect_structure_zones


def _candle(index: int, *, open_: str, high: str, low: str, close: str) -> Candle:
    open_time = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)
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
        volume=Decimal("10"),
        trade_count=10,
    )


def test_detect_bullish_and_bearish_fvg() -> None:
    candles = [
        _candle(0, open_="100", high="101", low="99", close="100"),
        _candle(1, open_="100", high="105", low="100.5", close="104.5"),
        _candle(2, open_="104.7", high="106", low="102.5", close="105.5"),
        _candle(3, open_="105.4", high="107.0", low="103.0", close="106.2"),
        _candle(4, open_="110.0", high="111.0", low="109.5", close="110.8"),
        _candle(5, open_="110.6", high="110.8", low="107.0", close="107.4"),
        _candle(6, open_="107.2", high="107.4", low="104.5", close="105.0"),
    ]

    zones = detect_fair_value_gaps(candles, FeatureSettings())

    assert any(zone.kind == "fvg" and zone.side == "bullish" for zone in zones)
    assert any(zone.kind == "fvg" and zone.side == "bearish" for zone in zones)


def test_detect_structure_zones_excludes_mitigated_fvg() -> None:
    candles = [
        _candle(0, open_="100", high="101", low="99", close="100"),
        _candle(1, open_="100", high="105", low="100.5", close="104.5"),
        _candle(2, open_="104.7", high="106", low="102.5", close="105.5"),
        _candle(3, open_="105.4", high="106", low="100.8", close="101.2"),
    ]

    zones = detect_structure_zones(candles, FeatureSettings())

    assert not any(zone.kind == "fvg" for zone in zones)


def test_detect_bullish_and_bearish_order_block() -> None:
    candles = [
        _candle(0, open_="100", high="101", low="99.5", close="100.5"),
        _candle(1, open_="100.4", high="100.7", low="98.8", close="99.0"),
        _candle(2, open_="99.2", high="101.5", low="99.1", close="101.3"),
        _candle(3, open_="101.2", high="103.0", low="101.0", close="102.8"),
        _candle(4, open_="102.7", high="104.0", low="102.4", close="103.6"),
        _candle(5, open_="103.8", high="105.2", low="103.6", close="104.9"),
        _candle(6, open_="104.8", high="106.1", low="104.5", close="105.8"),
        _candle(7, open_="105.7", high="106.0", low="104.0", close="104.2"),
        _candle(8, open_="104.1", high="104.3", low="101.8", close="102.0"),
        _candle(9, open_="101.9", high="102.0", low="99.6", close="100.2"),
        _candle(10, open_="100.3", high="100.5", low="97.4", close="98.0"),
    ]

    zones = detect_order_blocks(candles, FeatureSettings())

    assert any(zone.kind == "order_block" and zone.side == "bullish" for zone in zones)
    assert any(zone.kind == "order_block" and zone.side == "bearish" for zone in zones)
