"""
One-time Google Calendar OAuth setup.
Run: python3 setup_google_calendar.py
Opens browser for consent, saves token to ~/.config/job-search/google_token.json
"""
import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_FILE = Path.home() / ".job-search-gmail" / "credentials.json"
TOKEN_DIR = Path.home() / ".config" / "job-search"
TOKEN_FILE = TOKEN_DIR / "google_token.json"


def main():
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes),
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
        print(f"✓ Token saved to {TOKEN_FILE}")

    # Quick test
    from googleapiclient.discovery import build
    service = build("calendar", "v3", credentials=creds)
    cal = service.calendars().get(calendarId="primary").execute()
    print(f"✓ Connected to calendar: {cal['summary']} ({cal['id']})")
    print("\nGoogle Calendar is now configured. The app's Add to Calendar button will work.")


if __name__ == "__main__":
    main()
