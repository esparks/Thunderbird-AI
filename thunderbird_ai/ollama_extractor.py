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
            "enum": ["doctor_appointment", "vacation", "bill_due",
                     "payment_confirmation", "none"],
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

SYSTEM_PROMPT = """You classify a single personal email into exactly ONE category:

- doctor_appointment: a CONFIRMED medical/dental/vet appointment for THIS person,
  with a specific future date (and usually a time). Not marketing from a clinic.
- vacation: THIS person's own trip with real travel dates — a flight, hotel, or
  rental BOOKING CONFIRMATION or itinerary. NOT travel ads, deal emails, or price
  alerts.
- bill_due: a bill/invoice/statement this person still has to PAY, with an amount
  and a FUTURE due date. This is the "you owe money, pay by X" case.
- payment_confirmation: an email confirming that a payment this person owed was
  SCHEDULED, PROCESSED, POSTED, or PAID (a loan, credit-card, utility, or medical
  payment, or an autopay/direct-debit that pays a bill). The point is to confirm
  it's handled so no follow-up is needed.
- none: EVERYTHING else — newsletters, marketing, promotions, social/LinkedIn
  notifications, order/shipping updates, password resets, price/listing alerts,
  and money COMING IN to this person (deposits, "EFT received", refunds, person-
  to-person money received). When unsure, choose none.

Hard rules:
- ALWAYS fill "title": a short human label, e.g. "National Grid electric bill",
  "Fidelity card payment posted", "Dr. Patel cleaning". Never leave title empty.
- Also fill "payee_or_provider".
- date = the due date (bill_due), the appointment date, the vacation start, or the
  date the payment was made (payment_confirmation). YYYY-MM-DD; times 24h HH:MM.
  Never invent a date.
- amount = dollars as a number; 0 if unknown.
- confidence 0.0-1.0 for the category AND date; use < 0.6 if it's a guess.

Examples:
- "Your National Grid bill of $140.85 is due 10/10" -> {"category":"bill_due",
  "title":"National Grid electric bill","payee_or_provider":"National Grid",
  "date":"2026-10-10","amount":140.85,"confidence":0.97}
- "Fidelity Credit Card Payment Posted" -> {"category":"payment_confirmation",
  "title":"Fidelity card payment posted","payee_or_provider":"Fidelity",
  "date":"2026-09-09","confidence":0.95}
- "AmeriCU loan payment scheduled successfully" ->
  {"category":"payment_confirmation","title":"AmeriCU loan payment scheduled",
  "payee_or_provider":"AmeriCU","confidence":0.95}
- "EFT received / deposit to your account" -> {"category":"none","confidence":0.95}
- "50% off flights to Europe!" -> {"category":"none","confidence":0.95}
- "Reservation at Marriott, check-in Feb 13 2027" -> {"category":"vacation",
  "title":"Marriott stay","payee_or_provider":"Marriott","date":"2027-02-13",
  "confidence":0.9}
- "LinkedIn: 3 new notifications" -> {"category":"none","confidence":0.98}

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

    RELEVANT = {"doctor_appointment", "vacation", "bill_due", "payment_confirmation"}
    NEEDS_DATE = {"doctor_appointment", "vacation", "bill_due"}

    @property
    def is_relevant(self) -> bool:
        return self.category in self.RELEVANT


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
            f"body:\n{body[:2000]}"
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
            # num_ctx caps context so a big email can't balloon prompt-eval time
            # on a CPU-only box; num_predict caps the (small) JSON output.
            "options": {"temperature": 0, "num_predict": 300, "num_ctx": 4096},
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
