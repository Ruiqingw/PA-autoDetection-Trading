from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from config.settings import Settings
from data.models import BookLevel, BookSnapshot, Candle, Trade
from features.orderflow import BidAskIndicator, DeltaIndicator, TradeFlowSnapshot
from features.response import MarketResponseMetrics
from features.timeseries import CandleFeaturePoint
from services.monitor import MonitorBundle
from signals.composite import MonitorSnapshot
from webapp.serializers import build_dashboard_payload


def _candle(index: int, close: str) -> Candle:
    open_time = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index * 5)
    return Candle(
        symbol="BTC/USD",
        interval_minutes=5,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=5),
        open=Decimal(close),
        high=Decimal(close) + Decimal("2"),
        low=Decimal(close) - Decimal("2"),
        close=Decimal(close),
        vwap=Decimal(close),
        volume=Decimal("10"),
        trade_count=5,
    )


def test_build_dashboard_payload_includes_bundle_and_watchlist() -> None:
    candles = [_candle(0, "100"), _candle(1, "102")]
    trade_flow = TradeFlowSnapshot(
        symbol="BTC/USD",
        trade_count=10,
        buy_volume=Decimal("6"),
        sell_volume=Decimal("4"),
        total_volume=Decimal("10"),
        buy_strength=0.6,
        sell_strength=0.4,
        normalized_delta=0.2,
    )
    snapshot = MonitorSnapshot(
        symbol="BTC/USD",
        timeframe="5m",
        trade_flow=trade_flow,
        delta_indicator=DeltaIndicator(
            trade_count=10,
            buy_volume=Decimal("6"),
            sell_volume=Decimal("4"),
            total_volume=Decimal("10"),
            raw_delta=Decimal("2"),
            normalized_delta=0.2,
            buy_ratio=0.6,
            sell_ratio=0.4,
        ),
        bid_ask_indicator=BidAskIndicator(
            best_bid_price=Decimal("101"),
            best_ask_price=Decimal("101.1"),
            best_bid_volume=Decimal("3"),
            best_ask_volume=Decimal("2"),
            spread=Decimal("0.1"),
            spread_bps=9.9,
            top_of_book_imbalance=0.2,
            depth_imbalance=0.1,
            bid_ask_volume_ratio=1.5,
            depth_levels=5,
        ),
        spread={"spread": "0.1", "spread_bps": 9.9, "mid_price": "101.05"},
        book_imbalance=0.1,
        response=MarketResponseMetrics(
            price_return=0.01,
            market_response=0.05,
            blocked_buying_score=0.0,
            blocked_selling_score=0.0,
        ),
        bearish_flow_score=0.2,
        signal=None,
    )
    bundle = MonitorBundle(
        symbol="BTC/USD",
        interval_minutes=5,
        candles=candles,
        trades=[
            Trade(
                symbol="BTC/USD",
                price=Decimal("101"),
                volume=Decimal("1"),
                side="buy",
                order_type="market",
                timestamp=candles[0].open_time,
            )
        ],
        book_snapshot=BookSnapshot(
            symbol="BTC/USD",
            timestamp=candles[-1].close_time,
            bids=[BookLevel(price=Decimal("101"), volume=Decimal("3"))],
            asks=[BookLevel(price=Decimal("101.1"), volume=Decimal("2"))],
        ),
        analysis=snapshot,
        candle_feature_series=[
            CandleFeaturePoint(
                candle=candle,
                trade_count=5,
                buy_strength=0.6,
                sell_strength=0.4,
                normalized_delta=0.2,
                price_return=0.01,
                market_response=0.05,
                blocked_buying_score=0.0,
                blocked_selling_score=0.0,
                imbalance_label=None,
                imbalance_reason=None,
            )
            for candle in candles
        ],
        candle_footprints=[],
        imbalance_markers=[],
    )

    payload = build_dashboard_payload([bundle], Settings.from_env(), selected_symbol="BTC/USD", selected_interval=5)

    assert payload["selected_symbol"] == "BTC/USD"
    assert payload["selected_interval"] == 5
    assert payload["watchlist"][0]["display_symbol"] == "BTCUSD"
    assert payload["bundles"]["BTC/USD"]["interval_label"] == "5m"
    assert len(payload["bundles"]["BTC/USD"]["candles"]) == 2
