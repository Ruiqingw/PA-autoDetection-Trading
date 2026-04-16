# Crypto Trading Assistant

Discretionary crypto trading assistant built on Kraken public market data.

This project is designed for human-in-the-loop trading, not blind auto-execution. It fetches public market data, stores it locally, computes order-flow and market-response features, detects explicit price-action setups, and surfaces the results through scripts, alerts, and a lightweight TradingView-inspired desktop dashboard.

## What It Does

- Monitors `BTC/USD`, `ETH/USD`, and `SOL/USD`
- Pulls Kraken public `OHLC`, `Trades`, and `Depth` data
- Stores normalized market data in local SQLite
- Computes order-flow style indicators such as:
  - trade delta
  - buy/sell strength
  - spread
  - book imbalance
  - blocked buying / blocked selling
- Builds per-candle feature series for chart overlays and indicator panes
- Detects a first-pass bearish breakdown / retest style setup
- Supports optional Telegram and email alerts
- Includes a desktop GUI with:
  - TradingView-style shell
  - interactive chart pan / zoom
  - candle and footprint modes
  - selectable indicator panes
  - watchlist and current setup panel

## What It Is Not

By default, this repository does not:

- place live orders
- use private exchange credentials
- connect to account endpoints
- run automated execution strategies

The default product direction is research, monitoring, and decision support.

## Current Status

The repository currently includes both:

- a backend monitoring pipeline
- a local desktop GUI

It is already usable for exploratory monitoring and indicator research, but it is still an early-stage trading research tool rather than a finished production platform.

## Supported Timeframes

The app and monitor currently support:

- `1m`
- `5m`
- `15m`
- `1h`
- `4h`
- `1d`

## Feature Summary

### Data

- Kraken public REST client
- Kraken WebSocket v2 client
- normalized typed data models
- local SQLite persistence for candles, trades, book snapshots, and signals

### Features and Signals

- trade-flow aggregation
- delta indicator
- bid/ask indicator
- top-of-book spread
- L2 book imbalance
- market response scoring
- blocked buying / blocked selling metrics
- per-candle feature series
- footprint-style aggregation prototype
- explicit bearish setup detection and composite monitoring snapshot

### UI

- TradingView-inspired layout
- interactive main chart with smooth pan / zoom
- crosshair and hover state
- visible-range high / low markers
- selectable indicator area below the chart
- indicator popup inside the app shell

## Quick Start

### 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 2. Run Tests

```bash
pytest
```

### 3. Launch the Desktop App

```bash
python -m scripts.run_gui
```

### 4. Run the Backend Monitor

```bash
python -m scripts.run_monitor --symbols BTC/USD ETH/USD SOL/USD --iterations 1
```

## Useful Commands

Fetch recent candles:

```bash
python -m scripts.fetch_ohlc --symbol BTC/USD --interval 240 --limit 50
```

Fetch recent trades:

```bash
python -m scripts.fetch_trades --symbol BTC/USD --limit 200
```

Stream public trades:

```bash
python -m scripts.stream_trades --symbol BTC/USD
```

Stream public book updates:

```bash
python -m scripts.stream_book --symbol BTC/USD --depth 10
```

## Configuration

Most strategy and monitoring settings live in:

[config/settings.py](/Users/ruiqing/Documents/Trading/config/settings.py)

This includes defaults for:

- symbols
- polling intervals
- REST limits
- feature thresholds
- footprint parameters
- setup detection thresholds

Environment variables are mainly used for environment-specific settings such as alert credentials.

## Alerts

Alerts are optional and modular.

Telegram:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Email:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `SMTP_USE_TLS`

Kraken public market data does not require private API keys.

## Project Structure

```text
alerts/    Alert sinks and formatting
config/    Typed settings and thresholds
data/      Kraken clients and normalized market-data models
features/  Order-flow, response, footprint, and time-series features
scripts/   Runnable entry points
services/  End-to-end monitoring orchestration
signals/   Setup detection and composite analysis
storage/   SQLite persistence
tests/     Unit tests
ui/        Desktop dashboard and chart rendering
```

## Limitations

- The GUI still relies on snapshot-style data refresh rather than a full streaming chart engine
- Order-flow continuity depends on captured public trade history
- Footprint mode is still an early prototype
- Setup detection is intentionally explicit and narrow, not a full discretionary trading model
- WebSocket support exists, but the default end-to-end path still leans on REST snapshots for simplicity

## Roadmap

- continuous WebSocket trade ingestion for more complete delta and footprint coverage
- richer indicator library and configurable panes
- stronger historical backfill and research exports
- improved signal journaling and alert review
- broader setup library beyond the initial bearish structure
- eventual comparative research / backtesting utilities

## Safety

This repository is intentionally conservative about execution.

Unless explicitly requested, it should remain:

- public-data only
- local-first
- research-oriented
- human-in-the-loop

## License

No license file is currently included. If you want this repository to be open for reuse, add a license before treating it as a public open-source package.
