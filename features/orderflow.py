"""Order-flow and book-state feature calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal

from data.models import BookSnapshot, TopOfBookQuote, Trade, to_top_of_book


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
class DeltaIndicator:
    """Trade delta indicator over a selected trade window.

    Formula:
    - buy_volume = sum(volume for buy trades)
    - sell_volume = sum(volume for sell trades)
    - total_volume = buy_volume + sell_volume
    - raw_delta = buy_volume - sell_volume
    - normalized_delta = raw_delta / total_volume
    - buy_ratio = buy_volume / total_volume
    - sell_ratio = sell_volume / total_volume

    Parameters:
    - trades: normalized public trade list
    - window_seconds: optional rolling cutoff for selecting recent trades

    Interpretation:
    - positive raw_delta / normalized_delta means aggressive buying dominated
    - negative values mean aggressive selling dominated

    Units:
    - volumes and raw_delta are in base-asset units
    - normalized_delta, buy_ratio, sell_ratio are unitless

    Edge cases:
    - if total_volume == 0, all ratio-style outputs are 0.0
    """

    trade_count: int
    buy_volume: Decimal
    sell_volume: Decimal
    total_volume: Decimal
    raw_delta: Decimal
    normalized_delta: float
    buy_ratio: float
    sell_ratio: float

    def as_dict(self) -> dict[str, object]:
        return {
            "trade_count": self.trade_count,
            "buy_volume": str(self.buy_volume),
            "sell_volume": str(self.sell_volume),
            "total_volume": str(self.total_volume),
            "raw_delta": str(self.raw_delta),
            "normalized_delta": self.normalized_delta,
            "buy_ratio": self.buy_ratio,
            "sell_ratio": self.sell_ratio,
        }


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


@dataclass(slots=True)
class BidAskIndicator:
    """Bid/ask indicator snapshot from the public book.

    Formula:
    - spread = best_ask - best_bid
    - spread_bps = (spread / mid_price) * 10,000
    - top_of_book_imbalance = (best_bid_volume - best_ask_volume) / (best_bid_volume + best_ask_volume)
    - depth_imbalance = (sum(bid_volume_i) - sum(ask_volume_i)) / (sum(bid_volume_i) + sum(ask_volume_i))
      for the first N levels
    - bid_ask_volume_ratio = best_bid_volume / best_ask_volume

    Parameters:
    - snapshot: public order-book snapshot
    - depth_levels: number of levels used for depth imbalance

    Interpretation:
    - positive imbalances mean bid-side pressure / support
    - negative imbalances mean ask-side pressure / offer dominance
    - tighter spread generally means easier execution and more competitive quoting

    Units:
    - prices and spread are in quote currency
    - volumes are in base-asset units
    - spread_bps, imbalances, and ratios are unitless

    Edge cases:
    - returns None when top-of-book quotes are unavailable
    - bid_ask_volume_ratio is None when best ask volume is zero
    """

    best_bid_price: Decimal
    best_ask_price: Decimal
    best_bid_volume: Decimal
    best_ask_volume: Decimal
    spread: Decimal
    spread_bps: float
    top_of_book_imbalance: float
    depth_imbalance: float
    bid_ask_volume_ratio: float | None
    depth_levels: int

    def as_dict(self) -> dict[str, object]:
        return {
            "best_bid_price": str(self.best_bid_price),
            "best_ask_price": str(self.best_ask_price),
            "best_bid_volume": str(self.best_bid_volume),
            "best_ask_volume": str(self.best_ask_volume),
            "spread": str(self.spread),
            "spread_bps": self.spread_bps,
            "top_of_book_imbalance": self.top_of_book_imbalance,
            "depth_imbalance": self.depth_imbalance,
            "bid_ask_volume_ratio": self.bid_ask_volume_ratio,
            "depth_levels": self.depth_levels,
        }


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


def compute_delta_indicator(trades: list[Trade], *, window_seconds: int | None = None) -> DeltaIndicator:
    """Compute a formal delta indicator from public trades."""

    flow = aggregate_trade_flow(trades, window_seconds=window_seconds)
    raw_delta = flow.buy_volume - flow.sell_volume
    return DeltaIndicator(
        trade_count=flow.trade_count,
        buy_volume=flow.buy_volume,
        sell_volume=flow.sell_volume,
        total_volume=flow.total_volume,
        raw_delta=raw_delta,
        normalized_delta=flow.normalized_delta,
        buy_ratio=flow.buy_strength,
        sell_ratio=flow.sell_strength,
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


def compute_bid_ask_indicator(snapshot: BookSnapshot, *, depth_levels: int = 5) -> BidAskIndicator | None:
    """Compute a formal bid/ask indicator from the current public book snapshot."""

    top_of_book = to_top_of_book(snapshot)
    spread_metrics = compute_top_of_book_spread(top_of_book)
    if top_of_book is None or spread_metrics is None:
        return None

    top_total = top_of_book.bid_volume + top_of_book.ask_volume
    if top_total == ZERO:
        top_of_book_imbalance = 0.0
    else:
        top_of_book_imbalance = float((top_of_book.bid_volume - top_of_book.ask_volume) / top_total)

    bid_ask_volume_ratio: float | None
    if top_of_book.ask_volume == ZERO:
        bid_ask_volume_ratio = None
    else:
        bid_ask_volume_ratio = float(top_of_book.bid_volume / top_of_book.ask_volume)

    return BidAskIndicator(
        best_bid_price=top_of_book.bid_price,
        best_ask_price=top_of_book.ask_price,
        best_bid_volume=top_of_book.bid_volume,
        best_ask_volume=top_of_book.ask_volume,
        spread=spread_metrics.spread,
        spread_bps=spread_metrics.spread_bps,
        top_of_book_imbalance=top_of_book_imbalance,
        depth_imbalance=compute_book_imbalance(snapshot, depth_levels=depth_levels),
        bid_ask_volume_ratio=bid_ask_volume_ratio,
        depth_levels=depth_levels,
    )
