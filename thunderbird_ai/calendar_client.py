"""Google Calendar writes (create events only).

Reuses an existing OAuth client (credentials.json) and token (token.json). If no
token exists, the first run opens a browser once to authorize.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
BILL_COLOR_ID = "11"  # tomato/red, matches existing bill styling


class CalendarClient:
    def __init__(self, credentials_file: Path, token_file: Path, timezone: str):
        self.timezone = timezone
        self.service = build("calendar", "v3", credentials=self._auth(credentials_file, token_file))

    def _auth(self, credentials_file: Path, token_file: Path) -> Credentials:
        creds: Credentials | None = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())
        return creds

    # --- creation helpers ---
    def create_appointment(self, calendar_id: str, summary: str, date: str,
                           time: str, location: str, description: str) -> dict:
        if time:
            start = f"{date}T{time}:00"
            end_dt = _combine(date, time) + dt.timedelta(hours=1)
            end = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
            body = {
                "summary": summary,
                "location": location,
                "description": description,
                "start": {"dateTime": start, "timeZone": self.timezone},
                "end": {"dateTime": end, "timeZone": self.timezone},
                "reminders": {"useDefault": False, "overrides": [
                    {"method": "popup", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 120},
                ]},
            }
        else:
            end = (_date(date) + dt.timedelta(days=1)).strftime("%Y-%m-%d")
            body = {
                "summary": summary,
                "location": location,
                "description": description,
                "start": {"date": date},
                "end": {"date": end},
                "reminders": {"useDefault": False, "overrides": [
                    {"method": "popup", "minutes": 24 * 60},
                ]},
            }
        return self._insert(calendar_id, body)

    def create_vacation(self, calendar_id: str, summary: str, start_date: str,
                        end_date: str, location: str, description: str) -> dict:
        # All-day; end date is exclusive in Google Calendar.
        last_day = _date(end_date) if end_date else _date(start_date)
        end = (last_day + dt.timedelta(days=1)).strftime("%Y-%m-%d")
        body = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"date": start_date},
            "end": {"date": end},
            "reminders": {"useDefault": False, "overrides": [
                {"method": "popup", "minutes": 3 * 24 * 60},
            ]},
        }
        return self._insert(calendar_id, body)

    def create_bill(self, calendar_id: str, summary: str, due_date: str,
                    description: str) -> dict:
        end = (_date(due_date) + dt.timedelta(days=1)).strftime("%Y-%m-%d")
        body = {
            "summary": summary,
            "description": description,
            "colorId": BILL_COLOR_ID,
            "start": {"date": due_date},
            "end": {"date": end},
            "reminders": {"useDefault": False, "overrides": [
                {"method": "popup", "minutes": 48 * 60},
                {"method": "popup", "minutes": 24 * 60},
            ]},
        }
        return self._insert(calendar_id, body)

    def _insert(self, calendar_id: str, body: dict) -> dict:
        return self.service.events().insert(calendarId=calendar_id, body=body).execute()


def _date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").date()


def _combine(date_str: str, time_str: str) -> dt.datetime:
    return dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
