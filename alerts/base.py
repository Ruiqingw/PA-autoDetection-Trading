"""Alert abstractions and orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class AlertMessage:
    title: str
    body: str


class AlertSink(Protocol):
    def send(self, message: AlertMessage) -> None:
        """Deliver an alert message."""


class AlertManager:
    """Dispatches alerts to one or more optional sinks."""

    def __init__(self, sinks: list[AlertSink] | None = None) -> None:
        self.sinks = sinks or []

    def send(self, message: AlertMessage) -> None:
        for sink in self.sinks:
            sink.send(message)
