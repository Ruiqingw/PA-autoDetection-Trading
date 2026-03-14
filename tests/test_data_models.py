from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from data.models import parse_ohlc_rows, parse_rest_trades


def test_parse_ohlc_rows_excludes_last_unfinished_by_default() -> None:
    rows = [
        [1_700_000_000, "100", "105", "95", "98", "99", "10", 5],
        [1_700_003_600, "98", "101", "96", "100", "99.5", "12", 8],
    ]
    candles = parse_ohlc_rows("BTC/USD", 60, rows)

    assert len(candles) == 1
    assert candles[0].symbol == "BTC/USD"
    assert candles[0].open == Decimal("100")
    assert candles[0].trade_count == 5


def test_parse_rest_trades_normalizes_side_and_timestamp() -> None:
    rows = [
        ["43000.1", "0.25", 1_700_000_000.0, "b", "l", ""],
        ["42995.5", "0.40", 1_700_000_001.0, "s", "m", ""],
    ]
    trades = parse_rest_trades("BTC/USD", rows)

    assert [trade.side for trade in trades] == ["buy", "sell"]
    assert trades[0].price == Decimal("43000.1")
    assert trades[1].order_type == "market"
    assert trades[0].timestamp == datetime.fromtimestamp(1_700_000_000.0, tz=UTC)
