"""Email alert sink for backup or summary notifications."""

from __future__ import annotations

from email.message import EmailMessage
import smtplib

from alerts.base import AlertMessage
from config.settings import EmailSettings


class EmailAlertSink:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, message: AlertMessage) -> None:
        if not self.settings.enabled:
            return
        email = EmailMessage()
        email["Subject"] = message.title
        email["From"] = self.settings.sender
        email["To"] = self.settings.recipient
        email.set_content(message.body)

        with smtplib.SMTP(self.settings.host, self.settings.port) as smtp:
            if self.settings.use_tls:
                smtp.starttls()
            if self.settings.username and self.settings.password:
                smtp.login(self.settings.username, self.settings.password)
            smtp.send_message(email)
