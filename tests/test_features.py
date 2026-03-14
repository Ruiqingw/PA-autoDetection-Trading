from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from data.models import BookLevel, BookSnapshot, TopOfBookQuote, Trade
from features.orderflow import aggregate_trade_flow, compute_book_imbalance, compute_top_of_book_spread
from features.response import (
    compute_blocked_buying_score,
    compute_blocked_selling_score,
    compute_market_response,
    compute_response_metrics,
)


def _trade(side: str, price: str, volume: str, seconds: int) -> Trade:
    return Trade(
        symbol="BTC/USD",
        price=Decimal(price),
        volume=Decimal(volume),
        side=side,
        order_type="limit",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
    )


def test_aggregate_trade_flow() -> None:
    trades = [
        _trade("buy", "100", "2", 0),
        _trade("sell", "99", "1", 10),
        _trade("sell", "98", "1", 20),
    ]
    flow = aggregate_trade_flow(trades)

    assert flow.trade_count == 3
    assert flow.buy_volume == Decimal("2")
    assert flow.sell_volume == Decimal("2")
    assert flow.buy_strength == 0.5
    assert flow.normalized_delta == 0.0


def test_book_imbalance_and_spread() -> None:
    snapshot = BookSnapshot(
        symbol="BTC/USD",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        bids=[BookLevel(price=Decimal("100"), volume=Decimal("5")), BookLevel(price=Decimal("99"), volume=Decimal("3"))],
        asks=[BookLevel(price=Decimal("101"), volume=Decimal("2")), BookLevel(price=Decimal("102"), volume=Decimal("2"))],
    )
    imbalance = compute_book_imbalance(snapshot, depth_levels=2)
    spread = compute_top_of_book_spread(
        TopOfBookQuote(
            symbol="BTC/USD",
            timestamp=snapshot.timestamp,
            bid_price=Decimal("100"),
            bid_volume=Decimal("5"),
            ask_price=Decimal("101"),
            ask_volume=Decimal("2"),
        )
    )

    assert round(imbalance, 4) == 0.3333
    assert spread is not None
    assert spread.spread == Decimal("1")
    assert round(spread.spread_bps, 4) == 99.5025


def test_market_response_and_blocked_scores() -> None:
    response = compute_response_metrics(
        start_price=Decimal("100"),
        end_price=Decimal("99.8"),
        normalized_delta=0.4,
        min_flow=0.05,
        response_scale_bps=25.0,
    )

    assert round(response.price_return, 4) == -0.002
    assert round(response.market_response, 4) == -0.005
    assert response.blocked_buying_score > 0.9
    assert response.blocked_selling_score == 0.0


def test_blocked_selling_score() -> None:
    score = compute_blocked_selling_score(-0.8, -0.0005, response_scale_bps=25.0)
    assert 0.5 < score <= 1.0

    assert compute_blocked_buying_score(-0.5, 0.001) == 0.0
    assert compute_market_response(0.001, -0.5, min_flow=0.05) == 0.002
