"""Typed application settings and strategy thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


DEFAULT_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
DEFAULT_INTERVALS = [1, 5, 15, 60, 240, 1440]


def format_timeframe_label(interval_minutes: int) -> str:
    """Convert Kraken interval minutes into a user-facing label."""

    if interval_minutes < 60:
        return f"{interval_minutes}m"
    if interval_minutes < 1440 and interval_minutes % 60 == 0:
        return f"{interval_minutes // 60}h"
    if interval_minutes == 1440:
        return "1d"
    return f"{interval_minutes}m"


@dataclass(slots=True)
class StorageSettings:
    sqlite_path: Path = Path("artifacts/trading_assistant.sqlite3")


@dataclass(slots=True)
class RestSettings:
    base_url: str = "https://api.kraken.com/0/public"
    timeout_seconds: float = 10.0
    ohlc_limit: int = 200
    trade_limit: int = 1000
    depth_levels: int = 10


@dataclass(slots=True)
class WebSocketSettings:
    url: str = "wss://ws.kraken.com/v2"
    reconnect_delay_seconds: float = 5.0
    heartbeat_timeout_seconds: float = 30.0
    book_depth: int = 10


@dataclass(slots=True)
class FeatureSettings:
    trade_flow_window_seconds: int = 900
    response_scale_bps: float = 25.0
    min_flow_for_response: float = 0.05
    book_depth_levels: int = 5
    footprint_levels_per_candle: int = 6
    footprint_min_price_increment: float = 0.01
    imbalance_strength_threshold: float = 0.60
    imbalance_blocked_threshold: float = 0.55
    imbalance_min_trade_count: int = 5
    fvg_min_gap_ratio: float = 0.0005
    ob_displacement_ratio: float = 0.003
    ob_lookahead_candles: int = 3
    ob_lookback_candles: int = 3
    structure_zone_limit: int = 8


@dataclass(slots=True)
class BearishSetupSettings:
    selloff_lookback_candles: int = 4
    consolidation_candles: int = 3
    min_selloff_return: float = -0.025
    max_consolidation_range_ratio: float = 0.45
    breakdown_close_buffer: float = 0.001
    retest_tolerance: float = 0.003
    retest_rejection_close_buffer: float = 0.0005
    min_bearish_flow_score: float = 0.15


@dataclass(slots=True)
class MonitorSettings:
    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    intervals: list[int] = field(default_factory=lambda: list(DEFAULT_INTERVALS))
    poll_seconds: int = 60
    persist_signals: bool = True


@dataclass(slots=True)
class TelegramSettings:
    bot_token: str | None = None
    chat_id: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(slots=True)
class EmailSettings:
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    sender: str | None = None
    recipient: str | None = None
    use_tls: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.sender and self.recipient)


@dataclass(slots=True)
class Settings:
    storage: StorageSettings = field(default_factory=StorageSettings)
    rest: RestSettings = field(default_factory=RestSettings)
    websocket: WebSocketSettings = field(default_factory=WebSocketSettings)
    features: FeatureSettings = field(default_factory=FeatureSettings)
    bearish_setup: BearishSetupSettings = field(default_factory=BearishSetupSettings)
    monitor: MonitorSettings = field(default_factory=MonitorSettings)
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    email: EmailSettings = field(default_factory=EmailSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        sqlite_default = StorageSettings().sqlite_path
        return cls(
            storage=StorageSettings(
                sqlite_path=Path(os.getenv("TRADING_SQLITE_PATH", str(sqlite_default)))
            ),
            telegram=TelegramSettings(
                bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            ),
            email=EmailSettings(
                host=os.getenv("SMTP_HOST"),
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME"),
                password=os.getenv("SMTP_PASSWORD"),
                sender=os.getenv("EMAIL_FROM"),
                recipient=os.getenv("EMAIL_TO"),
                use_tls=os.getenv("SMTP_USE_TLS", "true").lower() != "false",
            ),
        )
