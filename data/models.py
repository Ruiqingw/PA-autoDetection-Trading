"""Typed normalized market-data models used across the project."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


ASSET_CODE_ALIASES = {
    "XBT": "BTC",
}


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(UTC)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def normalize_asset_code(code: str) -> str:
    if code in ASSET_CODE_ALIASES:
        return ASSET_CODE_ALIASES[code]
    if len(code) == 4 and code[0] in {"X", "Z"}:
        return ASSET_CODE_ALIASES.get(code[1:], code[1:])
    return ASSET_CODE_ALIASES.get(code, code)


def normalize_symbol(value: str) -> str:
    if "/" in value:
        base, quote = value.split("/", 1)
        return f"{normalize_asset_code(base)}{('/' + normalize_asset_code(quote))}"
    if len(value) >= 6:
        for quote in ("USD", "EUR", "USDT"):
            if value.endswith(quote):
                base = value[: -len(quote)]
                return f"{normalize_asset_code(base)}/{normalize_asset_code(quote)}"
    return value


@dataclass(slots=True)
class AssetPair:
    symbol: str
    rest_pair: str
    altname: str
    wsname: str | None = None
    base: str | None = None
    quote: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Candle:
    symbol: str
    interval_minutes: int
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    vwap: Decimal
    volume: Decimal
    trade_count: int
    source: str = "kraken_rest"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["open_time"] = self.open_time.isoformat()
        data["close_time"] = self.close_time.isoformat()
        return data


@dataclass(slots=True)
class Trade:
    symbol: str
    price: Decimal
    volume: Decimal
    side: str
    order_type: str | None
    timestamp: datetime
    trade_id: str | None = None
    source: str = "kraken_rest"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(slots=True)
class BookLevel:
    price: Decimal
    volume: Decimal


@dataclass(slots=True)
class BookSnapshot:
    symbol: str
    timestamp: datetime
    bids: list[BookLevel]
    asks: list[BookLevel]
    checksum: str | None = None
    source: str = "kraken_rest"


@dataclass(slots=True)
class TopOfBookQuote:
    symbol: str
    timestamp: datetime
    bid_price: Decimal
    bid_volume: Decimal
    ask_price: Decimal
    ask_volume: Decimal
    source: str = "kraken_rest"

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")


@dataclass(slots=True)
class SignalRecord:
    symbol: str
    timeframe: str
    setup_name: str
    detected_at: datetime
    support_level: Decimal
    entry_trigger: Decimal
    invalidation_level: Decimal
    confidence_score: float
    notes: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["detected_at"] = self.detected_at.isoformat()
        data["support_level"] = str(self.support_level)
        data["entry_trigger"] = str(self.entry_trigger)
        data["invalidation_level"] = str(self.invalidation_level)
        return data


def parse_asset_pairs(payload: dict[str, Any]) -> list[AssetPair]:
    pairs: list[AssetPair] = []
    for rest_pair, item in payload.items():
        wsname = item.get("wsname")
        altname = item.get("altname", rest_pair)
        symbol_source = wsname or altname or rest_pair
        symbol = normalize_symbol(symbol_source.replace("XBT", "BTC"))
        base, quote = (symbol.split("/", 1) + [None])[:2]
        pairs.append(
            AssetPair(
                symbol=symbol,
                rest_pair=rest_pair,
                altname=altname,
                wsname=wsname,
                base=base,
                quote=quote,
            )
        )
    return pairs


def parse_ohlc_rows(
    symbol: str,
    interval_minutes: int,
    rows: list[list[Any]],
    *,
    exclude_last_unfinished: bool = True,
) -> list[Candle]:
    selected_rows = rows[:-1] if exclude_last_unfinished and len(rows) > 1 else rows
    candles: list[Candle] = []
    for row in selected_rows:
        open_time = _as_datetime(row[0])
        close_time = open_time + timedelta(minutes=interval_minutes)
        candles.append(
            Candle(
                symbol=normalize_symbol(symbol),
                interval_minutes=interval_minutes,
                open_time=open_time,
                close_time=close_time,
                open=_as_decimal(row[1]),
                high=_as_decimal(row[2]),
                low=_as_decimal(row[3]),
                close=_as_decimal(row[4]),
                vwap=_as_decimal(row[5]),
                volume=_as_decimal(row[6]),
                trade_count=int(row[7]),
            )
        )
    return candles


def parse_rest_trades(symbol: str, rows: list[list[Any]]) -> list[Trade]:
    trades: list[Trade] = []
    for row in rows:
        side = "buy" if row[3] == "b" else "sell"
        trades.append(
            Trade(
                symbol=normalize_symbol(symbol),
                price=_as_decimal(row[0]),
                volume=_as_decimal(row[1]),
                timestamp=_as_datetime(row[2]),
                side=side,
                order_type="market" if row[4] == "m" else "limit",
            )
        )
    return trades


def parse_depth_snapshot(symbol: str, payload: dict[str, Any]) -> BookSnapshot:
    timestamp = datetime.now(tz=UTC)

    def _levels(entries: list[list[Any]]) -> list[BookLevel]:
        return [BookLevel(price=_as_decimal(price), volume=_as_decimal(volume)) for price, volume, *_ in entries]

    return BookSnapshot(
        symbol=normalize_symbol(symbol),
        timestamp=timestamp,
        bids=_levels(payload.get("bids", [])),
        asks=_levels(payload.get("asks", [])),
    )


def to_top_of_book(snapshot: BookSnapshot) -> TopOfBookQuote | None:
    if not snapshot.bids or not snapshot.asks:
        return None
    best_bid = snapshot.bids[0]
    best_ask = snapshot.asks[0]
    return TopOfBookQuote(
        symbol=snapshot.symbol,
        timestamp=snapshot.timestamp,
        bid_price=best_bid.price,
        bid_volume=best_bid.volume,
        ask_price=best_ask.price,
        ask_volume=best_ask.volume,
        source=snapshot.source,
    )
