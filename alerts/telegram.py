"""Telegram alert sink for primary real-time notifications."""

from __future__ import annotations

import httpx

from alerts.base import AlertMessage
from config.settings import TelegramSettings


class TelegramAlertSink:
    def __init__(self, settings: TelegramSettings) -> None:
        self.settings = settings

    def send(self, message: AlertMessage) -> None:
        if not self.settings.enabled:
            return
        url = f"https://api.telegram.org/bot{self.settings.bot_token}/sendMessage"
        text = f"*{message.title}*\n\n{message.body}"
        response = httpx.post(
            url,
            json={
                "chat_id": self.settings.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        response.raise_for_status()
