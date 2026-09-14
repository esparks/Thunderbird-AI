"""Tie the pieces together: for each email, extract -> decide -> act -> notify."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging

from .calendar_client import CalendarClient
from .config import Config
from .imap_client import Email, ImapReader
from .notifier import DiscordNotifier
from .ollama_extractor import Extraction, OllamaExtractor
from .state import State

log = logging.getLogger(__name__)


def _event_key(ext: Extraction) -> str:
    basis = "|".join([
        ext.category,
        ext.payee_or_provider.lower(),
        ext.date,
        ext.time,
        f"{ext.amount:.2f}",
    ])
    return hashlib.sha256(basis.encode()).hexdigest()[:20]


def _money(amount: float) -> str:
    return f"${amount:,.2f}" if amount else ""


class Pipeline:
    def __init__(self, cfg: Config, state: State):
        self.cfg = cfg
        self.state = state
        self.imap = ImapReader(
            cfg.imap_host, cfg.imap_port, cfg.imap_username, cfg.imap_password,
            cfg.imap_use_starttls, cfg.imap_exclude_folders,
        )
        self.extractor = OllamaExtractor(cfg.ollama_host, cfg.ollama_model, timeout=cfg.ollama_timeout)
        self.notifier = DiscordNotifier(
            mode=cfg.discord_mode,
            bot_token=cfg.discord_bot_token,
            channel_finances=cfg.discord_channel_finances,
            channel_personal=cfg.discord_channel_personal,
            webhook_finances=cfg.discord_webhook_finances,
            webhook_personal=cfg.discord_webhook_personal,
        )
        # Calendar is created lazily so a config/IMAP-only test run needs no Google auth.
        self._calendar: CalendarClient | None = None

    @property
    def calendar(self) -> CalendarClient:
        if self._calendar is None:
            self._calendar = CalendarClient(
                self.cfg.google_credentials_file, self.cfg.google_token_file, self.cfg.timezone
            )
        return self._calendar

    def run_once(self) -> None:
        today = dt.date.today().isoformat()
        emails = self.imap.fetch_recent(self.cfg.lookback_days)
        log.info("Fetched %d recent message(s).", len(emails))
        for mail in emails:
            if self.state.is_message_processed(mail.message_id):
                continue
            try:
                self._handle(mail, today)
            except Exception as exc:
                log.exception("Failed handling message %s: %s", mail.message_id, exc)

    def _handle(self, mail: Email, today: str) -> None:
        ext = self.extractor.extract(
            today=today, email_date=mail.date, sender=mail.sender,
            subject=mail.subject, body=mail.body,
        )
        if not ext.is_relevant or not ext.date:
            self.state.mark_message_processed(mail.message_id, mail.folder, ext.category, "skip", None)
            return

        key = _event_key(ext)
        if self.state.event_exists(key):
            self.state.mark_message_processed(mail.message_id, mail.folder, ext.category, "duplicate", None)
            return

        low = ext.confidence < self.cfg.confidence_threshold
        flag = "⚠️ *low confidence — please verify* " if low else ""

        if self.cfg.dry_run:
            log.info("[DRY_RUN] would create %s: %s on %s (conf %.2f)",
                     ext.category, ext.title or ext.payee_or_provider, ext.date, ext.confidence)
            self.state.mark_message_processed(mail.message_id, mail.folder, ext.category, "dry_run", None)
            return

        if ext.category == "bill":
            self._do_bill(mail, ext, key, flag)
        elif ext.category == "doctor_appointment":
            self._do_appointment(mail, ext, key, flag)
        elif ext.category == "vacation":
            self._do_vacation(mail, ext, key, flag)

    def _do_bill(self, mail: Email, ext: Extraction, key: str, flag: str) -> None:
        payee = ext.payee_or_provider or ext.title or "Bill"
        amount = _money(ext.amount)
        summary = f"{payee} — {amount}".rstrip(" —") if amount else payee
        desc = f"From email: {mail.subject}\nSender: {mail.sender}\n{ext.notes}".strip()
        event = self.calendar.create_bill(self.cfg.gcal_bills_calendar_id, summary, ext.date, desc)
        self.state.record_event(key, event["id"], self.cfg.gcal_bills_calendar_id, "bill", summary)
        self.state.mark_message_processed(mail.message_id, mail.folder, "bill", "created", event["id"])
        link = event.get("htmlLink", "")
        self.notifier.notify_bill(
            f"{flag}\U0001f4b3 **Bill added:** {summary} due **{ext.date}**\n{link}"
        )

    def _do_appointment(self, mail: Email, ext: Extraction, key: str, flag: str) -> None:
        who = ext.payee_or_provider or ext.title or "Appointment"
        summary = ext.title or f"Appointment — {who}"
        desc = f"From email: {mail.subject}\nSender: {mail.sender}\n{ext.notes}".strip()
        event = self.calendar.create_appointment(
            self.cfg.gcal_personal_calendar_id, summary, ext.date, ext.time, ext.location, desc
        )
        self.state.record_event(key, event["id"], self.cfg.gcal_personal_calendar_id, "doctor_appointment", summary)
        self.state.mark_message_processed(mail.message_id, mail.folder, "doctor_appointment", "created", event["id"])
        when = f"{ext.date} {ext.time}".strip()
        link = event.get("htmlLink", "")
        self.notifier.notify_personal(
            f"{flag}\U0001fa7a **Appointment added:** {summary} on **{when}**"
            + (f" @ {ext.location}" if ext.location else "") + f"\n{link}"
        )

    def _do_vacation(self, mail: Email, ext: Extraction, key: str, flag: str) -> None:
        summary = ext.title or f"Vacation — {ext.location or 'trip'}"
        desc = f"From email: {mail.subject}\nSender: {mail.sender}\n{ext.notes}".strip()
        event = self.calendar.create_vacation(
            self.cfg.gcal_personal_calendar_id, summary, ext.date, ext.end_date, ext.location, desc
        )
        self.state.record_event(key, event["id"], self.cfg.gcal_personal_calendar_id, "vacation", summary)
        self.state.mark_message_processed(mail.message_id, mail.folder, "vacation", "created", event["id"])
        span = ext.date + (f" → {ext.end_date}" if ext.end_date else "")
        link = event.get("htmlLink", "")
        self.notifier.notify_personal(
            f"{flag}\U0001f3d6️ **Vacation added:** {summary} (**{span}**)\n{link}"
        )
