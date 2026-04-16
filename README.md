# Crypto Trading Assistant

Discretionary crypto trading assistant built around Kraken public market data.

This version now includes both the backend monitoring pipeline and a local GUI application. It fetches public market data, normalizes and stores it locally, computes first-pass order-flow and market-response features, detects a simple bearish breakdown-retest setup, and can display buy/sell strength plus flow-vs-price imbalances directly on the chart. Optional Telegram and email alerts are also supported.

Supported chart / fetch timeframes in the app:
- `1m`
- `5m`
- `15m`
- `1h`
- `4h`
- `1d`

## Implemented in v0.1

- Kraken public REST client for `AssetPairs`, `OHLC`, `Trades`, and `Depth`
- Kraken WebSocket v2 public client for `ohlc`, `trade`, and `book`
- Internal typed market-data models and normalization helpers
- SQLite storage for asset pairs, candles, trades, top-of-book rows, and signals
- Local GUI application with:
  - price chart
  - buy/sell strength chart
  - imbalance markers drawn on the chart
  - current metrics and latest setup summary
- Feature calculations for:
  - normalized buy/sell strength
  - rolling trade-flow aggregation
  - top-of-book spread
  - L2 book imbalance
  - market response
  - blocked-buying and blocked-selling prototype scores
- Time-aligned candle feature series for charting:
  - per-candle buy strength
  - per-candle sell strength
  - per-candle blocked-buying / blocked-selling flags
- Configurable bearish price-action detector
- Composite monitor script that fetches data, computes features, detects setups, stores outputs, and can send alerts
- Example scripts for REST fetches and WebSocket subscriptions
- Unit tests for normalization, feature logic, and bearish setup detection

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run Examples

Fetch 4h candles:

```bash
python -m scripts.fetch_ohlc --symbol BTC/USD --interval 240 --limit 50
```

Fetch recent trades:

```bash
python -m scripts.fetch_trades --symbol BTC/USD --limit 200
```

Subscribe to BTC/USD trades:

```bash
python -m scripts.stream_trades --symbol BTC/USD
```

Subscribe to BTC/USD L2 book:

```bash
python -m scripts.stream_book --symbol BTC/USD --depth 10
```

Run the backend monitor loop:

```bash
python -m scripts.run_monitor --symbols BTC/USD ETH/USD SOL/USD --iterations 1
```

Launch the GUI application:

```bash
python -m scripts.run_gui
```

## Alerts

Alerts are modular and optional.

Telegram is the primary real-time alert channel:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Email can be used as a backup or summary channel:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `SMTP_USE_TLS`

No API keys are required for Kraken market data.

## Run Tests

```bash
pytest
```

## Current Limitations

- No historical backfill batching beyond simple recent REST pulls
- WebSocket handling is intentionally simple and does not maintain a full local L2 book state
- The GUI refreshes from REST snapshots and uses recent trades to build per-candle strength overlays
- Bearish setup detection is a first-pass explicit rules engine, not a complete discretionary chart model
- Alert deduplication is minimal
- The monitor and GUI primarily use REST snapshots for end-to-end operation; WebSocket examples are provided separately for live streaming research

## Suggested Next Steps

- Add historical backfill jobs and parquet exports
- Expand feature research around flow/response regimes
- Maintain incremental book state from WebSocket updates
- Add richer alert throttling and signal journaling
- Introduce comparative evaluation and later backtesting utilities
