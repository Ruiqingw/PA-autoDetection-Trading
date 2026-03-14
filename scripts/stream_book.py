"""Subscribe to Kraken WebSocket v2 L2 book for a symbol."""

from __future__ import annotations

import argparse
import asyncio
import json

from config.settings import Settings
from data.kraken_ws import KrakenWebSocketClient, parse_ws_book_message
from data.models import to_top_of_book


async def run(symbol: str, depth: int) -> None:
    settings = Settings.from_env()
    client = KrakenWebSocketClient(settings.websocket)
    async for message in client.subscribe("book", [symbol], depth=depth):
        snapshots = parse_ws_book_message(message.payload)
        for snapshot in snapshots:
            top = to_top_of_book(snapshot)
            if top is None:
                continue
            print(
                json.dumps(
                    {
                        "symbol": snapshot.symbol,
                        "timestamp": snapshot.timestamp.isoformat(),
                        "bid_price": str(top.bid_price),
                        "bid_volume": str(top.bid_volume),
                        "ask_price": str(top.ask_price),
                        "ask_volume": str(top.ask_volume),
                    }
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--depth", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run(args.symbol, args.depth))


if __name__ == "__main__":
    main()
