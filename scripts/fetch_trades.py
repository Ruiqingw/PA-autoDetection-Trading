"""Fetch recent trades from Kraken public REST."""

from __future__ import annotations

import argparse
import json

from config.settings import Settings
from data.kraken_rest import KrakenRestClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    settings = Settings.from_env()
    with KrakenRestClient(settings.rest) as client:
        trades = client.get_trades(args.symbol, limit=args.limit)
    payload = [trade.as_dict() for trade in trades]
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
