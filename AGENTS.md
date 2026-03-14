# Project Overview

This repository is a crypto trading assistant for discretionary trading.
It is not an auto-execution trading bot by default.

The system should help monitor BTC, ETH, and SOL, detect price-action setups,
compute order-flow and market-response metrics, and generate alerts to support manual trading decisions.

# Primary Goals

1. Detect price-action setups on crypto markets, especially:
   - impulsive selloff
   - contraction / triangle-like consolidation
   - breakdown below support
   - retest failure
   - short bias confirmation

2. Build order-flow style indicators using market data, including:
   - buy/sell strength
   - market response to buy/sell strength
   - blocked / absorbed buying
   - blocked / absorbed selling
   - book imbalance and spread context

3. Generate alerts, summaries, logs, and optional dashboards
   for human decision-making.

# Non-Goals

Unless explicitly requested, do NOT:
- place live orders
- connect to private trading endpoints
- use account credentials
- implement automated execution
- build a production trading bot

Default behavior is:
- fetch public market data
- compute features
- detect setups
- score signals
- generate alerts
- save logs / research outputs

# Data Source Policy

Default market data source is Kraken public market data.

Use Kraken public endpoints and channels first:
- REST:
  - AssetPairs
  - OHLC
  - Trades
  - Depth
- WebSocket v2:
  - ohlc
  - trade
  - book

Use these default symbols:
- BTC/USD
- ETH/USD
- SOL/USD

Do not use authenticated or private Kraken endpoints unless explicitly requested.

# Trading Style Context

This project is designed for discretionary price-action trading with order-flow confirmation.

The main price-action idea currently targeted is:

- fast selloff
- consolidation near support / lower boundary
- downside break
- retest of broken support
- rejection / failure to reclaim
- short confirmation

The order-flow idea currently targeted is:

- estimate buy/sell strength from public market data
- measure how strongly price responds to that strength
- identify cases where buying is strong but price does not move up much
- identify cases where selling is strong but price does not move down much
- use these as confirmation or warning signals

# Architecture Rules

Keep the code modular.

Preferred high-level structure:

- data/
  - exchange clients
  - ingestion
  - schemas / models
- features/
  - order-flow metrics
  - market-response metrics
  - rolling statistics
- signals/
  - price-action setup detection
  - combined signal scoring
- alerts/
  - notifications
  - formatting
- storage/
  - local persistence
- config/
  - settings and thresholds
- scripts/
  - runnable examples and jobs
- tests/
  - unit tests

Separate these concerns clearly:
- raw data fetching
- normalization / parsing
- feature computation
- signal generation
- alert generation
- persistence

Do not mix all logic into a single file.

# Implementation Priorities

Prioritize work in this order:

1. backend-only data ingestion
2. feature computation
3. signal detection
4. alert generation
5. research / backfill scripts
6. lightweight dashboard
7. execution module only if explicitly requested

Do not start with a heavy GUI.

# Safety Rules for Trading Code

Never add live order placement unless explicitly requested.

If execution-related code is ever added:
- isolate it in its own module
- disable it by default
- keep paper/simulated behavior separate from live behavior
- require explicit opt-in configuration

Do not assume permission to trade.

# Indicator Rules

Every new indicator must include:

1. a clear mathematical definition
2. parameter definitions
3. expected interpretation
4. units or normalization details where relevant
5. edge-case handling

Avoid vague heuristics without explicit formulas.

When implementing a metric, prefer pure functions that are easy to test.

Examples of acceptable indicator definitions:
- normalized delta
- rolling return
- range-adjusted return
- signed flow efficiency
- book imbalance
- blocked-buying score
- blocked-selling score

# Price-Action Signal Rules

Price-action setup detection should be explicit and configurable.

Avoid vague pattern labels without rules.

For each setup detector, define:
- prerequisites
- lookback windows
- thresholds
- invalidation logic
- output fields

Signal output should be structured, not freeform text.

Prefer a typed result or dictionary with fields such as:
- symbol
- timeframe
- setup_name
- detected_at
- support_level
- resistance_level
- entry_zone
- invalidation_level
- confidence_score
- notes

# Configuration Rules

All thresholds and tunable values must live in config, not be hard-coded in the logic.

Examples:
- symbol lists
- OHLC intervals
- trade aggregation windows
- lookback lengths
- contraction thresholds
- retest tolerance
- score cutoffs
- alert thresholds
- websocket depth
- storage paths

Use environment variables only for environment-specific or secret values.
Do not use env vars for every normal strategy parameter.

# Coding Style Rules

Use Python 3.11+.

Prefer:
- dataclasses, pydantic models, or typed dictionaries where useful
- type hints
- small functions
- readable names
- docstrings on important modules and functions
- explicit return values

Avoid:
- giant scripts
- hidden global state
- hard-coded magic numbers
- tightly coupled modules
- overly clever abstractions too early

# Testing Rules

Add unit tests for pure logic whenever practical.

Prioritize tests for:
- parsing Kraken payloads
- OHLC normalization
- trade aggregation
- book imbalance calculations
- market-response metrics
- setup detection logic
- signal scoring

For signal logic, prefer deterministic fixture-based tests.

# Storage Rules

Use local-first storage.

Preferred initial options:
- sqlite for structured local storage
- parquet or csv for research exports
- json for simple snapshots or config examples

Do not add heavy infrastructure unless clearly necessary.

# Logging Rules

Log important system behavior clearly:
- data fetch start/end
- websocket subscriptions
- reconnection events
- feature computation summaries
- signal detections
- alert deliveries
- errors and retries

Logs should help debug data quality and signal timing issues.

# Workflow Expectations

Before implementing a substantial feature:
- briefly summarize the plan
- identify files to create or modify

After implementing changes:
- summarize what changed
- explain how to run it
- explain how to verify it
- mention assumptions or limitations

If requirements are ambiguous, make a reasonable best effort aligned with this file instead of over-asking for clarification.

# Research-Friendly Development

This project is exploratory and research-oriented.

When useful, structure work so it supports:
- historical backfill
- offline feature research
- simple comparative experiments
- later backtesting
- later forward monitoring

Prefer reusable data and feature pipelines over one-off scripts.

# Suggested Initial Modules

A good initial scaffold should include modules similar to:

- data/kraken_rest.py
- data/kraken_ws.py
- data/models.py
- features/orderflow.py
- features/response.py
- signals/price_action.py
- signals/composite.py
- alerts/telegram.py
- storage/sqlite_store.py
- config/settings.py
- scripts/fetch_ohlc.py
- scripts/run_monitor.py

# Default Product Direction

The preferred first version is:

- backend-only
- Kraken public data only
- no private API credentials
- 1h and 4h OHLC support
- trade and L2 book support
- signal detection for short-side breakdown-retest structure
- order-flow confirmation metrics
- local logging and storage
- optional Telegram alerts

# Commands

If the repo does not already define commands, prefer adding support for:

- environment setup
- dependency installation
- test execution
- running a backfill script
- running a live monitor script

Example command targets may later include:
- `python -m scripts.fetch_ohlc`
- `python -m scripts.run_monitor`
- `pytest`

# Final Instruction

Read this file first and follow it as the default project guide.
When in doubt, favor:
- safety
- modularity
- explicit formulas
- configurability
- backend-first implementation
- human-in-the-loop usage