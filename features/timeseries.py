"""Time-aligned feature series for charts and GUI annotations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from config.settings import FeatureSettings
from data.models import Candle, Trade
from features.orderflow import aggregate_trade_flow
from features.response import compute_response_metrics


@dataclass(slots=True)
class CandleFeaturePoint:
    candle: Candle
    trade_count: int
    buy_strength: float
    sell_strength: float
    normalized_delta: float
    price_return: float
    market_response: float
    blocked_buying_score: float
    blocked_selling_score: float
    imbalance_label: str | None
    imbalance_reason: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "open_time": self.candle.open_time.isoformat(),
            "close_time": self.candle.close_time.isoformat(),
            "close": str(self.candle.close),
            "trade_count": self.trade_count,
            "buy_strength": self.buy_strength,
            "sell_strength": self.sell_strength,
            "normalized_delta": self.normalized_delta,
            "price_return": self.price_return,
            "market_response": self.market_response,
            "blocked_buying_score": self.blocked_buying_score,
            "blocked_selling_score": self.blocked_selling_score,
            "imbalance_label": self.imbalance_label,
            "imbalance_reason": self.imbalance_reason,
        }


@dataclass(slots=True)
class FlowPriceImbalance:
    timestamp: datetime
    price: Decimal
    label: str
    reason: str
    severity: float

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": str(self.price),
            "label": self.label,
            "reason": self.reason,
            "severity": self.severity,
        }


def _trades_for_candle(candle: Candle, trades: list[Trade]) -> list[Trade]:
    return [
        trade
        for trade in trades
        if candle.open_time <= trade.timestamp < candle.close_time
    ]


def classify_flow_price_imbalance(
    point: CandleFeaturePoint,
    settings: FeatureSettings,
) -> tuple[str | None, str | None]:
    """Flag candles where flow and price action visibly disagree.

    Rules:
    - Blocked buying:
      buy_strength >= threshold and either price_return <= 0 or blocked_buying_score >= threshold
    - Blocked selling:
      sell_strength >= threshold and either price_return >= 0 or blocked_selling_score >= threshold
    - Candles with too few trades are ignored to reduce noise.
    """

    if point.trade_count < settings.imbalance_min_trade_count:
        return None, None

    blocked_buying = (
        point.buy_strength >= settings.imbalance_strength_threshold
        and (
            point.price_return <= 0
            or point.blocked_buying_score >= settings.imbalance_blocked_threshold
        )
    )
    blocked_selling = (
        point.sell_strength >= settings.imbalance_strength_threshold
        and (
            point.price_return >= 0
            or point.blocked_selling_score >= settings.imbalance_blocked_threshold
        )
    )

    if blocked_buying and point.blocked_buying_score >= point.blocked_selling_score:
        return "Blocked buying", "Buy flow led but price failed to lift or sold off."
    if blocked_selling:
        return "Blocked selling", "Sell flow led but price failed to break lower or bounced."
    return None, None


def compute_candle_feature_series(
    candles: list[Candle],
    trades: list[Trade],
    settings: FeatureSettings,
) -> list[CandleFeaturePoint]:
    series: list[CandleFeaturePoint] = []
    for candle in candles:
        candle_trades = _trades_for_candle(candle, trades)
        flow = aggregate_trade_flow(candle_trades)
        response = compute_response_metrics(
            start_price=candle.open,
            end_price=candle.close,
            normalized_delta=flow.normalized_delta,
            min_flow=settings.min_flow_for_response,
            response_scale_bps=settings.response_scale_bps,
        )
        point = CandleFeaturePoint(
            candle=candle,
            trade_count=flow.trade_count,
            buy_strength=flow.buy_strength,
            sell_strength=flow.sell_strength,
            normalized_delta=flow.normalized_delta,
            price_return=response.price_return,
            market_response=response.market_response,
            blocked_buying_score=response.blocked_buying_score,
            blocked_selling_score=response.blocked_selling_score,
            imbalance_label=None,
            imbalance_reason=None,
        )
        point.imbalance_label, point.imbalance_reason = classify_flow_price_imbalance(point, settings)
        series.append(point)
    return series


def extract_imbalance_markers(series: list[CandleFeaturePoint]) -> list[FlowPriceImbalance]:
    markers: list[FlowPriceImbalance] = []
    for point in series:
        if point.imbalance_label is None or point.imbalance_reason is None:
            continue
        severity = max(point.blocked_buying_score, point.blocked_selling_score, abs(point.normalized_delta))
        markers.append(
            FlowPriceImbalance(
                timestamp=point.candle.close_time,
                price=point.candle.close,
                label=point.imbalance_label,
                reason=point.imbalance_reason,
                severity=severity,
            )
        )
    return markers
