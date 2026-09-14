"""Entry point: run the poll loop (or a single pass with --once)."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import APP_ROOT, Config
from .pipeline import Pipeline
from .state import State

LOG_FILE = APP_ROOT / "thunderbird_ai.log"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Thunderbird-AI email -> calendar agent")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    parser.add_argument("--check", action="store_true", help="Validate config and exit.")
    parser.add_argument("--auth", action="store_true",
                        help="Run the Google OAuth flow (opens a browser) and write token.json, then exit.")
    parser.add_argument("--test-discord", action="store_true",
                        help="Send one test message to each Discord channel and exit.")
    args = parser.parse_args()

    _setup_logging()
    log = logging.getLogger("thunderbird_ai")

    cfg = Config.load()
    problems = cfg.validate()
    if problems:
        log.error("Configuration problems:")
        for p in problems:
            log.error("  - %s", p)
        if args.check:
            return 1
        # IMAP password / calendar id / webhooks are hard requirements.
        return 1
    if args.check:
        log.info("Config OK. Model=%s  Poll=%ss  DryRun=%s",
                 cfg.ollama_model, cfg.poll_interval_seconds, cfg.dry_run)
        return 0

    if args.auth:
        from .calendar_client import CalendarClient
        log.info("Starting Google authorization (a browser window will open)...")
        CalendarClient(cfg.google_credentials_file, cfg.google_token_file, cfg.timezone)
        log.info("Google authorized. token.json written to %s", cfg.google_token_file)
        return 0

    if args.test_discord:
        from .notifier import DiscordNotifier
        n = DiscordNotifier(
            mode=cfg.discord_mode,
            bot_token=cfg.discord_bot_token,
            channel_finances=cfg.discord_channel_finances,
            channel_personal=cfg.discord_channel_personal,
            webhook_finances=cfg.discord_webhook_finances,
            webhook_personal=cfg.discord_webhook_personal,
        )
        n.notify_bill("✅ Thunderbird-AI test message to #finances")
        n.notify_personal("✅ Thunderbird-AI test message to #personal")
        log.info("Sent test messages (check #finances and #personal).")
        return 0

    state = State(APP_ROOT / "thunderbird_ai_state.db")
    pipeline = Pipeline(cfg, state)

    if args.once:
        pipeline.run_once()
        return 0

    log.info("Thunderbird-AI started. Polling every %ss.", cfg.poll_interval_seconds)
    while True:
        try:
            pipeline.run_once()
        except Exception as exc:
            log.exception("Poll cycle error: %s", exc)
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
