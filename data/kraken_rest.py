"""Kraken public REST client with normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from config.settings import RestSettings
from data.models import (
    AssetPair,
    BookSnapshot,
    Candle,
    Trade,
    parse_asset_pairs,
    parse_depth_snapshot,
    parse_ohlc_rows,
    parse_rest_trades,
)


DEFAULT_REST_PAIR_MAP = {
    "BTC/USD": "XBTUSD",
    "ETH/USD": "ETHUSD",
    "SOL/USD": "SOLUSD",
}


class KrakenRestClient:
    """Minimal Kraken REST client for public market-data endpoints."""

    def __init__(self, settings: RestSettings | None = None) -> None:
        self.settings = settings or RestSettings()
        self._client = httpx.Client(base_url=self.settings.base_url, timeout=self.settings.timeout_seconds)
        self._asset_pair_map: dict[str, str] = dict(DEFAULT_REST_PAIR_MAP)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KrakenRestClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("error", [])
        if errors:
            raise RuntimeError(f"Kraken REST error for {path}: {errors}")
        return payload["result"]

    def get_asset_pairs(self) -> list[AssetPair]:
        result = self._get("/AssetPairs")
        pairs = parse_asset_pairs(result)
        for pair in pairs:
            self._asset_pair_map[pair.symbol] = pair.altname or pair.rest_pair
        return pairs

    def resolve_rest_pair(self, symbol: str) -> str:
        if symbol in self._asset_pair_map:
            return self._asset_pair_map[symbol]
        pairs = self.get_asset_pairs()
        for pair in pairs:
            if pair.symbol == symbol:
                return pair.altname or pair.rest_pair
        raise KeyError(f"No Kraken REST pair mapping found for {symbol}")

    def get_ohlc(
        self,
        symbol: str,
        interval_minutes: int,
        *,
        since: int | None = None,
        exclude_last_unfinished: bool = True,
    ) -> list[Candle]:
        rest_pair = self.resolve_rest_pair(symbol)
        params: dict[str, Any] = {"pair": rest_pair, "interval": interval_minutes}
        if since is not None:
            params["since"] = since
        result = self._get("/OHLC", params=params)
        rows = result.get(rest_pair) or next(
            (value for key, value in result.items() if key != "last"),
            [],
        )
        return parse_ohlc_rows(
            symbol=symbol,
            interval_minutes=interval_minutes,
            rows=rows,
            exclude_last_unfinished=exclude_last_unfinished,
        )

    def get_trades(self, symbol: str, *, since: int | None = None, limit: int | None = None) -> list[Trade]:
        rest_pair = self.resolve_rest_pair(symbol)
        params: dict[str, Any] = {"pair": rest_pair}
        if since is not None:
            params["since"] = since
        result = self._get("/Trades", params=params)
        rows = result.get(rest_pair) or next(
            (value for key, value in result.items() if key != "last"),
            [],
        )
        trades = parse_rest_trades(symbol, rows)
        if limit is not None:
            return trades[-limit:]
        return trades

    def get_depth(self, symbol: str, *, count: int | None = None) -> BookSnapshot:
        rest_pair = self.resolve_rest_pair(symbol)
        params = {"pair": rest_pair, "count": count or self.settings.depth_levels}
        result = self._get("/Depth", params=params)
        payload = result.get(rest_pair) or next(iter(result.values()))
        return parse_depth_snapshot(symbol, payload)
