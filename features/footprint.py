"""Footprint-style candle aggregation for chart rendering."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from data.models import Candle, Trade


ZERO = Decimal("0")


@dataclass(slots=True)
class FootprintPriceLevel:
    lower_price: Decimal
    upper_price: Decimal
    buy_volume: Decimal
    sell_volume: Decimal
    total_volume: Decimal
    normalized_delta: float


@dataclass(slots=True)
class CandleFootprint:
    """Per-candle buy/sell volume summary for a footprint-like view.

    Definitions:
    - buy_volume: sum(volume for aggressive buy trades in the candle window)
    - sell_volume: sum(volume for aggressive sell trades in the candle window)
    - total_volume: buy_volume + sell_volume
    - buy_ratio: buy_volume / total_volume if total_volume > 0 else 0
    - sell_ratio: sell_volume / total_volume if total_volume > 0 else 0
    - normalized_delta: (buy_volume - sell_volume) / total_volume in [-1, 1]

    Interpretation:
    - positive normalized_delta means buying dominated the candle
    - negative normalized_delta means selling dominated the candle
    """

    candle: Candle
    trade_count: int
    buy_volume: Decimal
    sell_volume: Decimal
    total_volume: Decimal
    buy_ratio: float
    sell_ratio: float
    normalized_delta: float
    price_increment: Decimal
    price_levels: list[FootprintPriceLevel]


def _trades_for_candle(candle: Candle, trades: list[Trade]) -> list[Trade]:
    return [
        trade
        for trade in trades
        if candle.open_time <= trade.timestamp < candle.close_time
    ]


def _compute_price_increment(
    candle: Candle,
    *,
    levels_per_candle: int,
    min_price_increment: Decimal,
) -> Decimal:
    candle_range = candle.high - candle.low
    if candle_range <= ZERO:
        return min_price_increment
    raw_increment = candle_range / Decimal(levels_per_candle)
    return raw_increment if raw_increment > min_price_increment else min_price_increment


def _build_price_levels(
    candle: Candle,
    trades: list[Trade],
    *,
    price_increment: Decimal,
    levels_per_candle: int,
) -> list[FootprintPriceLevel]:
    if not trades:
        return []

    bucket_map: dict[int, dict[str, Decimal]] = {}
    max_bucket = max(levels_per_candle - 1, 0)
    for trade in trades:
        if price_increment <= ZERO:
            bucket_index = 0
        else:
            bucket_index = int((trade.price - candle.low) // price_increment)
        bucket_index = max(0, min(bucket_index, max_bucket))
        bucket = bucket_map.setdefault(bucket_index, {"buy": ZERO, "sell": ZERO})
        bucket[trade.side] = bucket.get(trade.side, ZERO) + trade.volume

    levels: list[FootprintPriceLevel] = []
    for bucket_index in sorted(bucket_map.keys(), reverse=True):
        lower_price = candle.low + price_increment * Decimal(bucket_index)
        upper_price = lower_price + price_increment
        buy_volume = bucket_map[bucket_index].get("buy", ZERO)
        sell_volume = bucket_map[bucket_index].get("sell", ZERO)
        total_volume = buy_volume + sell_volume
        normalized_delta = float((buy_volume - sell_volume) / total_volume) if total_volume else 0.0
        levels.append(
            FootprintPriceLevel(
                lower_price=lower_price,
                upper_price=upper_price,
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                total_volume=total_volume,
                normalized_delta=normalized_delta,
            )
        )
    return levels


def compute_candle_footprints(
    candles: list[Candle],
    trades: list[Trade],
    *,
    levels_per_candle: int = 10,
    min_price_increment: Decimal = Decimal("0.01"),
) -> list[CandleFootprint]:
    footprints: list[CandleFootprint] = []
    for candle in candles:
        candle_trades = _trades_for_candle(candle, trades)
        buy_volume = sum((trade.volume for trade in candle_trades if trade.side == "buy"), start=ZERO)
        sell_volume = sum((trade.volume for trade in candle_trades if trade.side == "sell"), start=ZERO)
        total_volume = buy_volume + sell_volume
        buy_ratio = float(buy_volume / total_volume) if total_volume else 0.0
        sell_ratio = float(sell_volume / total_volume) if total_volume else 0.0
        normalized_delta = float((buy_volume - sell_volume) / total_volume) if total_volume else 0.0
        price_increment = _compute_price_increment(
            candle,
            levels_per_candle=levels_per_candle,
            min_price_increment=min_price_increment,
        )
        footprints.append(
            CandleFootprint(
                candle=candle,
                trade_count=len(candle_trades),
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                total_volume=total_volume,
                buy_ratio=buy_ratio,
                sell_ratio=sell_ratio,
                normalized_delta=normalized_delta,
                price_increment=price_increment,
                price_levels=_build_price_levels(
                    candle,
                    candle_trades,
                    price_increment=price_increment,
                    levels_per_candle=levels_per_candle,
                ),
            )
        )
    return footprints
