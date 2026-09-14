"""Use a local Ollama model to extract structured info from an email.

Returns exactly one of: doctor_appointment, bill, vacation, or none.
Uses Ollama's structured-output (JSON schema) mode for reliable parsing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# JSON schema Ollama is asked to conform to.
SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["doctor_appointment", "bill", "vacation", "none"],
        },
        "title": {"type": "string"},
        "payee_or_provider": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD (due date / appt date / vacation start)"},
        "time": {"type": "string", "description": "HH:MM 24h, or empty if all-day/unknown"},
        "end_date": {"type": "string", "description": "YYYY-MM-DD vacation end, else empty"},
        "amount": {"type": "number"},
        "location": {"type": "string"},
        "confidence": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["category", "confidence"],
}

SYSTEM_PROMPT = """You extract calendar-worthy items from a single personal email.
You ONLY care about three things:
  - doctor_appointment: a medical/dental/vet appointment with a specific date.
  - bill: a bill, invoice, statement, or payment that is DUE by a specific date,
    with an amount if stated.
  - vacation: a trip / travel / hotel / flight booking with specific dates.
If the email is not clearly one of these (newsletters, marketing, receipts for
past purchases, order confirmations, generic notifications), return category
"none".

Rules:
- Resolve relative dates ("due in 5 days", "next Tuesday") using the provided
  "email received date" and "today" values. Output real calendar dates.
- Dates are YYYY-MM-DD. Times are 24h HH:MM. Leave a field empty if unknown.
- amount is a number in dollars (no symbols); 0 if unknown.
- confidence is 0.0-1.0: how sure you are of BOTH the category and the date.
- Never invent a date. If no concrete date is present, category is "none".
Return only the JSON object."""


@dataclass
class Extraction:
    category: str
    title: str
    payee_or_provider: str
    date: str
    time: str
    end_date: str
    amount: float
    location: str
    confidence: float
    notes: str

    @property
    def is_relevant(self) -> bool:
        return self.category in {"doctor_appointment", "bill", "vacation"}


def _coerce(data: dict) -> Extraction:
    def s(key: str) -> str:
        v = data.get(key, "")
        return str(v).strip() if v is not None else ""

    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    return Extraction(
        category=s("category") or "none",
        title=s("title"),
        payee_or_provider=s("payee_or_provider"),
        date=s("date"),
        time=s("time"),
        end_date=s("end_date"),
        amount=amount,
        location=s("location"),
        confidence=max(0.0, min(1.0, confidence)),
        notes=s("notes"),
    )


class OllamaExtractor:
    def __init__(self, host: str, model: str, timeout: int = 120):
        self.host = host
        self.model = model
        self.timeout = timeout

    def extract(self, *, today: str, email_date: str, sender: str,
                subject: str, body: str) -> Extraction:
        user = (
            f"today: {today}\n"
            f"email received date: {email_date}\n"
            f"from: {sender}\n"
            f"subject: {subject}\n\n"
            f"body:\n{body[:6000]}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": SCHEMA,
            "options": {"temperature": 0},
        }
        resp = requests.post(
            f"{self.host}/api/chat", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "{}")
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            log.warning("Model returned non-JSON; treating as 'none'. Raw: %.200s", content)
            data = {"category": "none", "confidence": 0.0}
        return _coerce(data)
