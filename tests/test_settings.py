from __future__ import annotations

from config.settings import format_timeframe_label


def test_format_timeframe_label() -> None:
    assert format_timeframe_label(1) == "1m"
    assert format_timeframe_label(5) == "5m"
    assert format_timeframe_label(15) == "15m"
    assert format_timeframe_label(60) == "1h"
    assert format_timeframe_label(240) == "4h"
    assert format_timeframe_label(1440) == "1d"
