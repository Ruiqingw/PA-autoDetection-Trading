from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from data.models import Trade
from storage.sqlite_store import SQLiteStore


def test_load_trades_returns_requested_time_window(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "market.sqlite3")
    base_time = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
    trades = [
        Trade(
            symbol="BTC/USD",
            price=Decimal("68000"),
            volume=Decimal("0.1"),
            side="buy",
            order_type="limit",
            timestamp=base_time,
        ),
        Trade(
            symbol="BTC/USD",
            price=Decimal("68010"),
            volume=Decimal("0.2"),
            side="sell",
            order_type="market",
            timestamp=base_time + timedelta(minutes=5),
        ),
        Trade(
            symbol="BTC/USD",
            price=Decimal("68020"),
            volume=Decimal("0.3"),
            side="buy",
            order_type="market",
            timestamp=base_time + timedelta(minutes=10),
        ),
    ]
    store.insert_trades(trades)

    selected = store.load_trades(
        "BTC/USD",
        start_time=base_time + timedelta(minutes=4),
        end_time=base_time + timedelta(minutes=11),
    )

    assert len(selected) == 2
    assert [trade.side for trade in selected] == ["sell", "buy"]
    assert selected[0].timestamp == base_time + timedelta(minutes=5)
    assert selected[1].volume == Decimal("0.3")
