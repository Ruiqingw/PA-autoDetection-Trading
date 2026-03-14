"""SQLite persistence for normalized market data and signals."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from data.models import AssetPair, BookSnapshot, Candle, SignalRecord, TopOfBookQuote, Trade, to_top_of_book


class SQLiteStore:
    """Local-first sqlite storage for research-friendly normalized data."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS asset_pairs (
                    symbol TEXT PRIMARY KEY,
                    rest_pair TEXT NOT NULL,
                    altname TEXT NOT NULL,
                    wsname TEXT,
                    base TEXT,
                    quote TEXT
                );

                CREATE TABLE IF NOT EXISTS ohlc_candles (
                    symbol TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    open_time TEXT NOT NULL,
                    close_time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    vwap REAL NOT NULL,
                    volume REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (symbol, interval_minutes, open_time)
                );

                CREATE TABLE IF NOT EXISTS trades (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT,
                    trade_id TEXT,
                    source TEXT NOT NULL,
                    PRIMARY KEY (symbol, timestamp, price, volume, side)
                );

                CREATE TABLE IF NOT EXISTS top_of_book (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    bid_price REAL NOT NULL,
                    bid_volume REAL NOT NULL,
                    ask_price REAL NOT NULL,
                    ask_volume REAL NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (symbol, timestamp, source)
                );

                CREATE TABLE IF NOT EXISTS signals (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    setup_name TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    support_level REAL NOT NULL,
                    entry_trigger REAL NOT NULL,
                    invalidation_level REAL NOT NULL,
                    confidence_score REAL NOT NULL,
                    notes TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, setup_name, detected_at)
                );
                """
            )

    def upsert_asset_pairs(self, pairs: list[AssetPair]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO asset_pairs(symbol, rest_pair, altname, wsname, base, quote)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    rest_pair=excluded.rest_pair,
                    altname=excluded.altname,
                    wsname=excluded.wsname,
                    base=excluded.base,
                    quote=excluded.quote
                """,
                [(pair.symbol, pair.rest_pair, pair.altname, pair.wsname, pair.base, pair.quote) for pair in pairs],
            )

    def upsert_candles(self, candles: list[Candle]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO ohlc_candles
                (symbol, interval_minutes, open_time, close_time, open, high, low, close, vwap, volume, trade_count, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval_minutes, open_time) DO UPDATE SET
                    close_time=excluded.close_time,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    vwap=excluded.vwap,
                    volume=excluded.volume,
                    trade_count=excluded.trade_count,
                    source=excluded.source
                """,
                [
                    (
                        candle.symbol,
                        candle.interval_minutes,
                        candle.open_time.isoformat(),
                        candle.close_time.isoformat(),
                        float(candle.open),
                        float(candle.high),
                        float(candle.low),
                        float(candle.close),
                        float(candle.vwap),
                        float(candle.volume),
                        candle.trade_count,
                        candle.source,
                    )
                    for candle in candles
                ],
            )

    def insert_trades(self, trades: list[Trade]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO trades
                (symbol, timestamp, price, volume, side, order_type, trade_id, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        trade.symbol,
                        trade.timestamp.isoformat(),
                        float(trade.price),
                        float(trade.volume),
                        trade.side,
                        trade.order_type,
                        trade.trade_id,
                        trade.source,
                    )
                    for trade in trades
                ],
            )

    def insert_book_snapshot(self, snapshot: BookSnapshot) -> None:
        top_of_book = to_top_of_book(snapshot)
        if top_of_book is None:
            return
        self.insert_top_of_book([top_of_book])

    def insert_top_of_book(self, quotes: list[TopOfBookQuote]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO top_of_book
                (symbol, timestamp, bid_price, bid_volume, ask_price, ask_volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        quote.symbol,
                        quote.timestamp.isoformat(),
                        float(quote.bid_price),
                        float(quote.bid_volume),
                        float(quote.ask_price),
                        float(quote.ask_volume),
                        quote.source,
                    )
                    for quote in quotes
                ],
            )

    def insert_signal(self, signal: SignalRecord) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO signals
                (symbol, timeframe, setup_name, detected_at, support_level, entry_trigger, invalidation_level, confidence_score, notes, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.symbol,
                    signal.timeframe,
                    signal.setup_name,
                    signal.detected_at.isoformat(),
                    float(signal.support_level),
                    float(signal.entry_trigger),
                    float(signal.invalidation_level),
                    signal.confidence_score,
                    signal.notes,
                    json.dumps(signal.metadata, sort_keys=True, default=str),
                ),
            )

    def latest_signal_timestamp(self, symbol: str, timeframe: str, setup_name: str) -> datetime | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT detected_at
                FROM signals
                WHERE symbol = ? AND timeframe = ? AND setup_name = ?
                ORDER BY detected_at DESC
                LIMIT 1
                """,
                (symbol, timeframe, setup_name),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None
