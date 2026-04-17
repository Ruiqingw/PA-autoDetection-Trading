"""Fetch recent OHLC candles from Kraken public REST."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from data.kraken_rest import KrakenRestClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--interval", type=int, default=240)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    settings = Settings.from_env()
    with KrakenRestClient(settings.rest) as client:
        candles = client.get_ohlc(args.symbol, args.interval)
    payload = [candle.as_dict() for candle in candles[-args.limit :]]
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
