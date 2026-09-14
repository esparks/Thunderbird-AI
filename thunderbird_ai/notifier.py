"""Discord notifications via incoming webhooks."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_finances: str, webhook_personal: str, timeout: int = 15):
        self.webhook_finances = webhook_finances
        self.webhook_personal = webhook_personal
        self.timeout = timeout

    def _post(self, url: str, content: str) -> None:
        if not url:
            log.warning("No Discord webhook configured; skipping: %s", content)
            return
        try:
            r = requests.post(url, json={"content": content[:1900]}, timeout=self.timeout)
            r.raise_for_status()
        except Exception as exc:
            log.error("Discord post failed: %s", exc)

    def notify_bill(self, content: str) -> None:
        self._post(self.webhook_finances, content)

    def notify_personal(self, content: str) -> None:
        self._post(self.webhook_personal, content)
