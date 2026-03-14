"""Order-flow and book-state feature calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal

from data.models import BookSnapshot, TopOfBookQuote, Trade


ZERO = Decimal("0")


@dataclass(slots=True)
class TradeFlowSnapshot:
    symbol: str
    trade_count: int
    buy_volume: Decimal
    sell_volume: Decimal
    total_volume: Decimal
    buy_strength: float
    sell_strength: float
    normalized_delta: float

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["buy_volume"] = str(self.buy_volume)
        data["sell_volume"] = str(self.sell_volume)
        data["total_volume"] = str(self.total_volume)
        return data


@dataclass(slots=True)
class SpreadMetrics:
    spread: Decimal
    spread_bps: float
    mid_price: Decimal

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["spread"] = str(self.spread)
        data["mid_price"] = str(self.mid_price)
        return data


def aggregate_trade_flow(trades: list[Trade], *, window_seconds: int | None = None) -> TradeFlowSnapshot:
    """Aggregate trade flow.

    Formula:
    - buy_volume = sum(volume for buy trades)
    - sell_volume = sum(volume for sell trades)
    - total_volume = buy_volume + sell_volume
    - buy_strength = buy_volume / total_volume
    - sell_strength = sell_volume / total_volume
    - normalized_delta = (buy_volume - sell_volume) / total_volume

    Interpretation:
    - `normalized_delta` is in [-1, 1]
    - positive means aggressive buying dominated the sample
    - negative means aggressive selling dominated the sample
    """

    selected = trades
    if window_seconds is not None and trades:
        cutoff = max(trade.timestamp for trade in trades) - timedelta(seconds=window_seconds)
        selected = [trade for trade in trades if trade.timestamp >= cutoff]
    buy_volume = sum((trade.volume for trade in selected if trade.side == "buy"), start=ZERO)
    sell_volume = sum((trade.volume for trade in selected if trade.side == "sell"), start=ZERO)
    total_volume = buy_volume + sell_volume
    if total_volume == ZERO:
        return TradeFlowSnapshot(
            symbol=selected[-1].symbol if selected else "",
            trade_count=len(selected),
            buy_volume=ZERO,
            sell_volume=ZERO,
            total_volume=ZERO,
            buy_strength=0.0,
            sell_strength=0.0,
            normalized_delta=0.0,
        )
    return TradeFlowSnapshot(
        symbol=selected[-1].symbol,
        trade_count=len(selected),
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        total_volume=total_volume,
        buy_strength=float(buy_volume / total_volume),
        sell_strength=float(sell_volume / total_volume),
        normalized_delta=float((buy_volume - sell_volume) / total_volume),
    )


def compute_top_of_book_spread(quote: TopOfBookQuote | None) -> SpreadMetrics | None:
    """Compute top-of-book spread.

    Formula:
    - spread = best_ask - best_bid
    - mid_price = (best_ask + best_bid) / 2
    - spread_bps = (spread / mid_price) * 10,000

    Units:
    - spread is in quote currency
    - spread_bps is basis points
    """

    if quote is None:
        return None
    mid_price = quote.mid_price
    if mid_price == ZERO:
        return SpreadMetrics(spread=ZERO, spread_bps=0.0, mid_price=ZERO)
    spread = quote.ask_price - quote.bid_price
    return SpreadMetrics(
        spread=spread,
        spread_bps=float((spread / mid_price) * Decimal("10000")),
        mid_price=mid_price,
    )


def compute_book_imbalance(snapshot: BookSnapshot, *, depth_levels: int = 5) -> float:
    """Compute L2 book imbalance.

    Formula:
    - bid_depth = sum(bid_volume_i for i in first N bid levels)
    - ask_depth = sum(ask_volume_i for i in first N ask levels)
    - imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

    Interpretation:
    - close to +1 means the near book is bid-heavy
    - close to -1 means the near book is ask-heavy
    - 0 means balanced
    """

    bid_depth = sum((level.volume for level in snapshot.bids[:depth_levels]), start=ZERO)
    ask_depth = sum((level.volume for level in snapshot.asks[:depth_levels]), start=ZERO)
    total_depth = bid_depth + ask_depth
    if total_depth == ZERO:
        return 0.0
    return float((bid_depth - ask_depth) / total_depth)
