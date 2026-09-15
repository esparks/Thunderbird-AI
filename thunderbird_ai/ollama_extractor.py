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
    },
    "required": ["category", "confidence"],
}

SYSTEM_PROMPT = """You extract calendar-worthy items from a single personal email.
Classify the email as exactly ONE category:

- doctor_appointment: a CONFIRMED medical/dental/vet appointment for THIS person,
  with a specific future date (and usually a time). Not marketing from a clinic.
- bill: a bill/invoice/statement with an amount and a specific FUTURE DUE date the
  person still has to PAY. It is NOT a bill if money has already moved or is just
  an alert: "payment posted/processed/received/scheduled/confirmed", "EFT
  received", "direct debit withdrawal", "deposit", "person to person payment",
  order confirmations, or receipts -> those are category none.
- vacation: THIS person's own trip with real travel dates — a flight, hotel, or
  rental BOOKING CONFIRMATION or itinerary. NOT travel ads, deal emails, price
  alerts, or any email that merely mentions a place or date.
- none: EVERYTHING else — newsletters, marketing, promotions, social/LinkedIn
  notifications, order/shipping updates, receipts, password resets, statements
  with no due date. When unsure, choose none.

Hard rules:
- ALWAYS fill "title": a short human label, e.g. "National Grid electric bill",
  "Dr. Patel dental cleaning", "Delta flight to Cancun". Never leave title empty.
- Also fill "payee_or_provider" (the company/provider/airline).
- Resolve relative dates using the given "email received date" and "today".
  Dates are YYYY-MM-DD, times 24h HH:MM. Never invent a date — if there is no
  concrete date, category is "none".
- amount is a number of dollars (no symbols); 0 if unknown.
- confidence 0.0-1.0 = how sure you are of the category AND the date. Use < 0.6
  if the category is a guess.

Examples:
- "Your National Grid bill of $140.85 is due 10/10" -> {"category":"bill",
  "title":"National Grid electric bill","payee_or_provider":"National Grid",
  "date":"2026-10-10","amount":140.85,"confidence":0.97}
- "50% off flights to Europe this weekend!" -> {"category":"none","confidence":0.95}
- "You're all set! Your reservation at Marriott, check-in Feb 13 2027" ->
  {"category":"vacation","title":"Marriott stay","payee_or_provider":"Marriott",
  "date":"2027-02-13","confidence":0.9}
- "LinkedIn: you have 3 new notifications" -> {"category":"none","confidence":0.98}
- "Fidelity Credit Card Payment Posted" -> {"category":"none","confidence":0.96}
- "Direct debit withdrawal from your account" -> {"category":"none","confidence":0.95}
- "AmeriCU Payment Scheduled Successfully" -> {"category":"none","confidence":0.95}

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

    def d(key: str) -> str:
        # Normalize any ISO datetime the model returns down to YYYY-MM-DD.
        v = s(key)
        return v.split("T")[0][:10] if "T" in v else v

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
        date=d("date"),
        time=s("time"),
        end_date=d("end_date"),
        amount=amount,
        location=s("location"),
        confidence=max(0.0, min(1.0, confidence)),
        notes=s("notes"),
    )


class OllamaExtractor:
    def __init__(self, host: str, model: str, timeout: int = 300):
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
            f"body:\n{body[:4000]}"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": SCHEMA,
            "keep_alive": "30m",  # keep the model loaded between emails
            "options": {"temperature": 0, "num_predict": 400},
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
