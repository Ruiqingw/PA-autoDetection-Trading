from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from data.models import Candle, Trade
from features.footprint import compute_candle_footprints


BASE_TIME = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)


def _candle(hours: int, open_price: str, close_price: str) -> Candle:
    open_time = BASE_TIME + timedelta(hours=hours)
    return Candle(
        symbol="BTC/USD",
        interval_minutes=60,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal(open_price),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(close_price),
        vwap=Decimal("100"),
        volume=Decimal("10"),
        trade_count=3,
    )


def _trade(hours: int, minutes: int, side: str, price: str, volume: str) -> Trade:
    return Trade(
        symbol="BTC/USD",
        price=Decimal(price),
        volume=Decimal(volume),
        side=side,
        order_type="market",
        timestamp=BASE_TIME + timedelta(hours=hours, minutes=minutes),
    )


def test_compute_candle_footprints_summarizes_buy_sell_volume_per_candle() -> None:
    candles = [_candle(0, "100", "100.5"), _candle(1, "100.5", "99.5")]
    trades = [
        _trade(0, 5, "buy", "100.1", "3"),
        _trade(0, 20, "sell", "100.0", "1"),
        _trade(1, 10, "sell", "99.8", "4"),
        _trade(1, 30, "buy", "99.9", "1"),
    ]

    footprints = compute_candle_footprints(
        candles,
        trades,
        levels_per_candle=4,
        min_price_increment=Decimal("0.25"),
    )

    assert len(footprints) == 2
    assert footprints[0].buy_volume == Decimal("3")
    assert footprints[0].sell_volume == Decimal("1")
    assert footprints[0].trade_count == 2
    assert footprints[0].buy_ratio == 0.75
    assert footprints[0].normalized_delta == 0.5
    assert footprints[0].price_increment == Decimal("0.5")
    assert len(footprints[0].price_levels) == 1
    assert footprints[0].price_levels[0].buy_volume == Decimal("3")
    assert footprints[0].price_levels[0].sell_volume == Decimal("1")
    assert footprints[1].buy_volume == Decimal("1")
    assert footprints[1].sell_volume == Decimal("4")
    assert footprints[1].sell_ratio == 0.8
    assert footprints[1].normalized_delta == -0.6
    assert len(footprints[1].price_levels) == 1
    assert footprints[1].price_levels[0].sell_volume == Decimal("4")
    assert footprints[1].price_levels[0].buy_volume == Decimal("1")
