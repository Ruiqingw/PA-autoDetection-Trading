"""Subscribe to Kraken WebSocket v2 trades for a symbol."""

from __future__ import annotations

import argparse
import asyncio
import json

from config.settings import Settings
from data.kraken_ws import KrakenWebSocketClient, parse_ws_trade_message


async def run(symbol: str) -> None:
    settings = Settings.from_env()
    client = KrakenWebSocketClient(settings.websocket)
    async for message in client.subscribe("trade", [symbol]):
        trades = parse_ws_trade_message(message.payload)
        for trade in trades:
            print(json.dumps(trade.as_dict()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USD")
    args = parser.parse_args()
    asyncio.run(run(args.symbol))


if __name__ == "__main__":
    main()
