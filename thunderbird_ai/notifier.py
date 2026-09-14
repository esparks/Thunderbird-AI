"""Discord notifications.

Two modes:
  - "bot": post as an existing Discord bot via the REST API (reuses the
    hq-agent-org bot token + channel IDs). No webhooks needed.
  - "webhook": post to incoming webhook URLs.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"


class DiscordNotifier:
    def __init__(
        self,
        mode: str = "bot",
        *,
        bot_token: str = "",
        channel_finances: str = "",
        channel_personal: str = "",
        webhook_finances: str = "",
        webhook_personal: str = "",
        timeout: int = 15,
    ):
        self.mode = mode.lower().strip()
        self.bot_token = bot_token
        self.channel_finances = channel_finances
        self.channel_personal = channel_personal
        self.webhook_finances = webhook_finances
        self.webhook_personal = webhook_personal
        self.timeout = timeout

    # --- public ---
    def notify_bill(self, content: str) -> None:
        self._send(content, self.channel_finances, self.webhook_finances, "#finances")

    def notify_personal(self, content: str) -> None:
        self._send(content, self.channel_personal, self.webhook_personal, "#personal")

    # --- internal ---
    def _send(self, content: str, channel_id: str, webhook_url: str, label: str) -> None:
        payload = {"content": content[:1900]}
        try:
            if self.mode == "bot":
                if not (self.bot_token and channel_id):
                    log.warning("Bot mode missing token/channel for %s; skipping.", label)
                    return
                r = requests.post(
                    f"{DISCORD_API}/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bot {self.bot_token}"},
                    json=payload,
                    timeout=self.timeout,
                )
            else:
                if not webhook_url:
                    log.warning("Webhook mode missing URL for %s; skipping.", label)
                    return
                r = requests.post(webhook_url, json=payload, timeout=self.timeout)
            r.raise_for_status()
        except Exception as exc:
            log.error("Discord post to %s failed: %s", label, exc)
