"""Read-only IMAP access.

Connects with STARTTLS, walks every folder except the excluded ones, and
returns recent messages as simple dicts. Every mailbox is opened read-only so
no flags are ever changed and nothing is moved or deleted.
"""

from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message

log = logging.getLogger(__name__)


@dataclass
class Email:
    message_id: str
    folder: str
    date: str
    sender: str
    subject: str
    body: str


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_body(msg: Message) -> str:
    """Prefer text/plain; fall back to a crude HTML strip."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            if ctype == "text/plain":
                plain_parts.append(_payload_text(part))
            elif ctype == "text/html":
                html_parts.append(_payload_text(part))
    else:
        if msg.get_content_type() == "text/html":
            html_parts.append(_payload_text(msg))
        else:
            plain_parts.append(_payload_text(msg))

    if plain_parts:
        return "\n".join(p for p in plain_parts if p).strip()
    if html_parts:
        return _strip_html("\n".join(html_parts)).strip()
    return ""


def _payload_text(part: Message) -> str:
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text


class ImapReader:
    def __init__(self, host: str, port: int, username: str, password: str,
                 use_starttls: bool, exclude_folders: list[str]):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_starttls = use_starttls
        self.exclude_folders = exclude_folders

    def _connect(self) -> imaplib.IMAP4:
        if self.port == 993 and not self.use_starttls:
            conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            conn = imaplib.IMAP4(self.host, self.port)
            if self.use_starttls:
                conn.starttls()
        conn.login(self.username, self.password)
        return conn

    def _folders(self, conn: imaplib.IMAP4) -> list[str]:
        typ, data = conn.list()
        if typ != "OK" or not data:
            return ["INBOX"]
        names: list[str] = []
        for raw in data:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            # Folder name is the last quoted token (or last space-delimited token).
            name = line.split(' "')[-1].strip().strip('"') if '"' in line else line.split()[-1]
            if any(x in name.lower() for x in self.exclude_folders):
                continue
            names.append(name)
        return names or ["INBOX"]

    def fetch_recent(self, lookback_days: int) -> list[Email]:
        since = (datetime.now() - timedelta(days=max(lookback_days, 0))).strftime("%d-%b-%Y")
        results: list[Email] = []
        conn = self._connect()
        try:
            for folder in self._folders(conn):
                try:
                    typ, _ = conn.select(f'"{folder}"', readonly=True)
                    if typ != "OK":
                        continue
                    typ, data = conn.search(None, "SINCE", since)
                    if typ != "OK" or not data or not data[0]:
                        continue
                    for num in data[0].split():
                        typ, msg_data = conn.fetch(num, "(RFC822)")
                        if typ != "OK" or not msg_data or not msg_data[0]:
                            continue
                        raw = msg_data[0][1]
                        msg = email.message_from_bytes(raw)
                        mid = (msg.get("Message-ID") or "").strip()
                        if not mid:
                            mid = f"{folder}:{num.decode()}:{msg.get('Date','')}"
                        results.append(
                            Email(
                                message_id=mid,
                                folder=folder,
                                date=_decode(msg.get("Date")),
                                sender=_decode(msg.get("From")),
                                subject=_decode(msg.get("Subject")),
                                body=_extract_body(msg),
                            )
                        )
                except Exception as exc:  # keep going on a bad folder/message
                    log.warning("IMAP folder %s error: %s", folder, exc)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return results
