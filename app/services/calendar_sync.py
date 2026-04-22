"""
Google Calendar sync — checks which events are already on Santiago's calendar.
Uses the Google Calendar API via service account or OAuth token stored in .env.
Falls back gracefully if not configured.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional


def _get_credentials():
    """Load OAuth2 credentials from environment or token file."""
    token_path = os.path.expanduser("~/.config/job-search/google_token.json")
    if os.path.exists(token_path):
        with open(token_path) as f:
            return json.load(f)
    return None


async def get_calendar_events_this_week() -> list[dict]:
    """
    Fetch events from Google Calendar for the next 7 days.
    Returns list of {summary, start, end, location, id}.
    Returns empty list if calendar not configured.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds_data = _get_credentials()
        if not creds_data:
            return []

        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
        )

        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        week_end = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

        result = service.events().list(
            calendarId="primary",
            timeMin=now,
            timeMax=week_end,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = []
        for item in result.get("items", []):
            events.append({
                "id": item["id"],
                "summary": item.get("summary", ""),
                "location": item.get("location", ""),
                "start": item["start"].get("dateTime", item["start"].get("date")),
                "end": item["end"].get("dateTime", item["end"].get("date")),
            })
        return events

    except Exception as e:
        print(f"[calendar_sync] Could not fetch calendar: {e}")
        return []


def check_event_in_calendar(event_name: str, calendar_events: list[dict]) -> bool:
    """Check if an event name roughly matches any calendar entry."""
    name_lower = event_name.lower()
    for cal_event in calendar_events:
        cal_name = cal_event.get("summary", "").lower()
        # Check for significant word overlap
        words = [w for w in name_lower.split() if len(w) > 4]
        if any(w in cal_name for w in words):
            return True
    return False
