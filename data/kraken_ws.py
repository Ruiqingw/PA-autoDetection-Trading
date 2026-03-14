"""Kraken WebSocket v2 public client with simple reconnect handling."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from decimal import Decimal
from typing import Any

import aiohttp

from config.settings import WebSocketSettings
from data.models import BookLevel, BookSnapshot, Candle, Trade, normalize_symbol


LOGGER = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.fromtimestamp(float(value), tz=UTC)


@dataclass(slots=True)
class WSMessage:
    channel: str
    payload: Any


def parse_ws_trade_message(message: dict[str, Any]) -> list[Trade]:
    trades: list[Trade] = []
    for item in message.get("data", []):
        symbol = normalize_symbol(item.get("symbol", ""))
        for trade in item.get("trades", item.get("data", [])):
            trades.append(
                Trade(
                    symbol=symbol,
                    price=_decimal(trade.get("price")),
                    volume=_decimal(trade.get("qty", trade.get("volume", "0"))),
                    side=str(trade.get("side", "")).lower(),
                    order_type=trade.get("ord_type"),
                    timestamp=_timestamp(trade.get("timestamp", trade.get("time"))),
                    trade_id=str(trade.get("trade_id")) if trade.get("trade_id") is not None else None,
                    source="kraken_ws",
                )
            )
    return trades


def parse_ws_book_message(message: dict[str, Any]) -> list[BookSnapshot]:
    snapshots: list[BookSnapshot] = []
    for item in message.get("data", []):
        bids = [BookLevel(price=_decimal(level["price"]), volume=_decimal(level["qty"])) for level in item.get("bids", [])]
        asks = [BookLevel(price=_decimal(level["price"]), volume=_decimal(level["qty"])) for level in item.get("asks", [])]
        snapshots.append(
            BookSnapshot(
                symbol=normalize_symbol(item.get("symbol", "")),
                timestamp=_timestamp(item.get("timestamp", datetime.now(tz=UTC).isoformat())),
                bids=bids,
                asks=asks,
                checksum=str(item.get("checksum")) if item.get("checksum") is not None else None,
                source="kraken_ws",
            )
        )
    return snapshots


def parse_ws_ohlc_message(message: dict[str, Any]) -> list[Candle]:
    candles: list[Candle] = []
    for item in message.get("data", []):
        interval = int(item.get("interval", item.get("interval_begin", 1)))
        open_time = _timestamp(item.get("interval_begin", item.get("timestamp")))
        close_time = _timestamp(item.get("interval_end", item.get("timestamp")))
        candles.append(
            Candle(
                symbol=normalize_symbol(item.get("symbol", "")),
                interval_minutes=interval,
                open_time=open_time,
                close_time=close_time,
                open=_decimal(item.get("open")),
                high=_decimal(item.get("high")),
                low=_decimal(item.get("low")),
                close=_decimal(item.get("close")),
                vwap=_decimal(item.get("vwap", item.get("close"))),
                volume=_decimal(item.get("volume", "0")),
                trade_count=int(item.get("trades", item.get("trade_count", 0))),
                source="kraken_ws",
            )
        )
    return candles


class KrakenWebSocketClient:
    """Simple public WebSocket v2 client for Kraken market-data streams."""

    def __init__(self, settings: WebSocketSettings | None = None) -> None:
        self.settings = settings or WebSocketSettings()

    async def subscribe(
        self,
        channel: str,
        symbols: list[str],
        *,
        depth: int | None = None,
    ) -> AsyncIterator[WSMessage]:
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self.settings.url, heartbeat=self.settings.heartbeat_timeout_seconds) as ws:
                        params: dict[str, Any] = {"channel": channel, "symbol": symbols}
                        if channel == "book":
                            params["depth"] = depth or self.settings.book_depth
                        await ws.send_json({"method": "subscribe", "params": params})
                        async for raw_message in ws:
                            if raw_message.type != aiohttp.WSMsgType.TEXT:
                                continue
                            message = json.loads(raw_message.data)
                            if message.get("channel") != channel:
                                continue
                            if message.get("type") in {"heartbeat", "status"}:
                                continue
                            yield WSMessage(channel=channel, payload=message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("WebSocket %s stream dropped: %s", channel, exc)
                await asyncio.sleep(self.settings.reconnect_delay_seconds)

    async def consume(
        self,
        channel: str,
        symbols: list[str],
        handler: Callable[[WSMessage], Any],
        *,
        depth: int | None = None,
    ) -> None:
        async for message in self.subscribe(channel, symbols, depth=depth):
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
