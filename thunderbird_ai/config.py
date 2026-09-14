"""Load and validate configuration from config.env (or the environment)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Application root = the directory that contains config.env, credentials, db, etc.
APP_ROOT = Path(__file__).resolve().parent.parent


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # IMAP
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    imap_use_starttls: bool
    imap_exclude_folders: list[str]

    # Polling
    poll_interval_seconds: int
    lookback_days: int

    # Ollama
    ollama_host: str
    ollama_model: str
    ollama_timeout: int

    # Google Calendar
    google_credentials_file: Path
    google_token_file: Path
    gcal_personal_calendar_id: str
    gcal_bills_calendar_id: str

    # Discord
    discord_mode: str
    discord_bot_token: str
    discord_channel_finances: str
    discord_channel_personal: str
    discord_webhook_finances: str
    discord_webhook_personal: str

    # Behavior
    confidence_threshold: float
    timezone: str
    dry_run: bool

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(APP_ROOT / "config.env")

        def _resolve(path_str: str) -> Path:
            p = Path(path_str)
            return p if p.is_absolute() else (APP_ROOT / p)

        cfg = cls(
            imap_host=os.getenv("IMAP_HOST", "dfw-r02.nixins.com"),
            imap_port=int(os.getenv("IMAP_PORT", "143")),
            imap_username=os.getenv("IMAP_USERNAME", ""),
            imap_password=os.getenv("IMAP_PASSWORD", ""),
            imap_use_starttls=_bool(os.getenv("IMAP_USE_STARTTLS"), True),
            imap_exclude_folders=[
                s.strip().lower()
                for s in os.getenv("IMAP_EXCLUDE_FOLDERS", "Trash,Junk,Spam,Archive").split(",")
                if s.strip()
            ],
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "900")),
            lookback_days=int(os.getenv("LOOKBACK_DAYS", "1")),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "300")),
            google_credentials_file=_resolve(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")),
            google_token_file=_resolve(os.getenv("GOOGLE_TOKEN_FILE", "token.json")),
            gcal_personal_calendar_id=os.getenv("GCAL_PERSONAL_CALENDAR_ID", "sparkserich@gmail.com"),
            gcal_bills_calendar_id=os.getenv("GCAL_BILLS_CALENDAR_ID", ""),
            discord_mode=os.getenv("DISCORD_MODE", "bot").strip().lower(),
            discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", ""),
            discord_channel_finances=os.getenv("DISCORD_CHANNEL_FINANCES", ""),
            discord_channel_personal=os.getenv("DISCORD_CHANNEL_PERSONAL", ""),
            discord_webhook_finances=os.getenv("DISCORD_WEBHOOK_FINANCES", ""),
            discord_webhook_personal=os.getenv("DISCORD_WEBHOOK_PERSONAL", ""),
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.6")),
            timezone=os.getenv("TIMEZONE", "America/New_York"),
            dry_run=_bool(os.getenv("DRY_RUN"), False),
        )
        return cfg

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty == OK)."""
        problems: list[str] = []
        if not self.imap_password:
            problems.append("IMAP_PASSWORD is empty (set it in config.env).")
        if not self.imap_username:
            problems.append("IMAP_USERNAME is empty.")
        if not self.gcal_bills_calendar_id:
            problems.append("GCAL_BILLS_CALENDAR_ID is empty.")
        if self.discord_mode == "bot":
            if not self.discord_bot_token:
                problems.append("DISCORD_BOT_TOKEN is empty (bot mode).")
            if not self.discord_channel_finances or not self.discord_channel_personal:
                problems.append("DISCORD_CHANNEL_FINANCES / DISCORD_CHANNEL_PERSONAL is empty (bot mode).")
        elif self.discord_mode == "webhook":
            if not self.discord_webhook_finances or not self.discord_webhook_personal:
                problems.append("DISCORD_WEBHOOK_FINANCES / DISCORD_WEBHOOK_PERSONAL is empty (webhook mode).")
        else:
            problems.append(f"DISCORD_MODE must be 'bot' or 'webhook' (got '{self.discord_mode}').")
        if not self.google_credentials_file.exists() and not self.google_token_file.exists():
            problems.append(
                f"Neither {self.google_credentials_file.name} nor "
                f"{self.google_token_file.name} found for Google auth."
            )
        return problems
