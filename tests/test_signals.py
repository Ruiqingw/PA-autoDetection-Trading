from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from config.settings import BearishSetupSettings
from data.models import Candle
from signals.price_action import detect_bearish_breakdown_retest


def _candle(index: int, open_: str, high: str, low: str, close: str) -> Candle:
    open_time = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=index)
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


def test_detect_bearish_breakdown_retest_signal() -> None:
    candles = [
        _candle(0, "110", "111", "106", "107"),
        _candle(1, "107", "108", "103", "104"),
        _candle(2, "104", "105", "100", "101"),
        _candle(3, "101", "102", "97", "98"),
        _candle(4, "98", "99", "97.5", "98.2"),
        _candle(5, "98.2", "98.7", "97.7", "98.0"),
        _candle(6, "98.0", "98.4", "97.6", "97.9"),
        _candle(7, "97.9", "98.0", "95.5", "95.8"),
        _candle(8, "96.2", "97.8", "95.7", "96.1"),
    ]

    signal = detect_bearish_breakdown_retest(
        candles,
        timeframe="60m",
        settings=BearishSetupSettings(),
        bearish_flow_score=0.5,
        blocked_buying_score=0.6,
        book_imbalance=-0.4,
    )

    assert signal is not None
    assert signal.symbol == "BTC/USD"
    assert signal.setup_name == "bearish_breakdown_retest"
    assert signal.support_level == Decimal("97.5")
    assert signal.confidence_score > 0.6


def test_detect_bearish_breakdown_retest_returns_none_without_retest_failure() -> None:
    candles = [
        _candle(0, "110", "111", "106", "107"),
        _candle(1, "107", "108", "103", "104"),
        _candle(2, "104", "105", "100", "101"),
        _candle(3, "101", "102", "97", "98"),
        _candle(4, "98", "99", "97.5", "98.2"),
        _candle(5, "98.2", "98.7", "97.7", "98.0"),
        _candle(6, "98.0", "98.4", "97.6", "97.9"),
        _candle(7, "97.9", "98.0", "95.5", "95.8"),
        _candle(8, "95.9", "98.1", "95.8", "97.9"),
    ]

    signal = detect_bearish_breakdown_retest(
        candles,
        timeframe="60m",
        settings=BearishSetupSettings(),
        bearish_flow_score=0.5,
        blocked_buying_score=0.6,
        book_imbalance=-0.4,
    )

    assert signal is None
