"""Composite monitoring pipeline combining data, features, and signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.settings import Settings
from data.models import BookSnapshot, Candle, SignalRecord, to_top_of_book, Trade
from features.orderflow import (
    SpreadMetrics,
    TradeFlowSnapshot,
    aggregate_trade_flow,
    compute_book_imbalance,
    compute_top_of_book_spread,
)
from features.response import MarketResponseMetrics, compute_response_metrics
from signals.price_action import detect_bearish_breakdown_retest


@dataclass(slots=True)
class MonitorSnapshot:
    symbol: str
    timeframe: str
    trade_flow: TradeFlowSnapshot
    spread: dict[str, Any] | None
    book_imbalance: float
    response: MarketResponseMetrics
    bearish_flow_score: float
    signal: SignalRecord | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trade_flow": self.trade_flow.as_dict(),
            "spread": self.spread,
            "book_imbalance": self.book_imbalance,
            "response": self.response.as_dict(),
            "bearish_flow_score": self.bearish_flow_score,
            "signal": self.signal.as_dict() if self.signal else None,
        }


def compute_bearish_flow_score(
    trade_flow: TradeFlowSnapshot,
    response: MarketResponseMetrics,
    book_imbalance: float,
) -> float:
    delta_component = max(0.0, -trade_flow.normalized_delta)
    response_component = max(0.0, -response.market_response * 100)
    imbalance_component = max(0.0, -book_imbalance)
    blocked_buy_component = response.blocked_buying_score
    score = (
        min(delta_component, 1.0) * 0.35
        + min(response_component, 1.0) * 0.25
        + min(imbalance_component, 1.0) * 0.20
        + min(blocked_buy_component, 1.0) * 0.20
    )
    return min(score, 1.0)


def analyze_market_state(
    *,
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    trades: list[Trade],
    book_snapshot: BookSnapshot,
    settings: Settings,
) -> MonitorSnapshot:
    trade_flow = aggregate_trade_flow(trades, window_seconds=settings.features.trade_flow_window_seconds)
    top_of_book = to_top_of_book(book_snapshot)
    spread_metrics = compute_top_of_book_spread(top_of_book)
    book_imbalance = compute_book_imbalance(
        book_snapshot,
        depth_levels=settings.features.book_depth_levels,
    )
    response = compute_response_metrics(
        start_price=candles[-2].close if len(candles) > 1 else candles[-1].open,
        end_price=candles[-1].close,
        normalized_delta=trade_flow.normalized_delta,
        min_flow=settings.features.min_flow_for_response,
        response_scale_bps=settings.features.response_scale_bps,
    )
    bearish_flow_score = compute_bearish_flow_score(trade_flow, response, book_imbalance)
    signal = detect_bearish_breakdown_retest(
        candles,
        timeframe=timeframe,
        settings=settings.bearish_setup,
        bearish_flow_score=bearish_flow_score,
        blocked_buying_score=response.blocked_buying_score,
        book_imbalance=book_imbalance,
    )
    if signal and bearish_flow_score < settings.bearish_setup.min_bearish_flow_score:
        signal = None
    return MonitorSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        trade_flow=trade_flow,
        spread=spread_metrics.as_dict() if spread_metrics else None,
        book_imbalance=book_imbalance,
        response=response,
        bearish_flow_score=bearish_flow_score,
        signal=signal,
    )
