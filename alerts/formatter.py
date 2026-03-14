"""Formatting helpers for user-facing alerts."""

from __future__ import annotations

import json

from alerts.base import AlertMessage
from data.models import SignalRecord


def format_signal_alert(signal: SignalRecord) -> AlertMessage:
    title = f"{signal.symbol} {signal.timeframe} {signal.setup_name}"
    body = "\n".join(
        [
            f"Detected at: {signal.detected_at.isoformat()}",
            f"Support: {signal.support_level}",
            f"Entry trigger: {signal.entry_trigger}",
            f"Invalidation: {signal.invalidation_level}",
            f"Confidence: {signal.confidence_score:.2f}",
            f"Notes: {signal.notes}",
            f"Metadata: {json.dumps(signal.metadata, sort_keys=True, default=str)}",
        ]
    )
    return AlertMessage(title=title, body=body)
