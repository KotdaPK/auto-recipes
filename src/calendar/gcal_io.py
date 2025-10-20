"""Google Calendar helpers: OAuth bootstrap and upsert events."""

from __future__ import annotations

import datetime
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def ensure_credentials(
    client_secrets: str = "credentials.json", token_file: str = "token.json"
) -> Credentials:
    """Ensure OAuth credentials exist, run local flow if needed."""
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf8") as fh:
            fh.write(creds.to_json())
    return creds


def upsert_event(
    meal_page_id: str,
    title: str,
    start_dt: datetime.datetime,
    duration_min: int,
    description_url: Optional[str] = None,
) -> str:
    """Create or patch an event, using extendedProperties.private.notion_page_id for idempotency.

    Returns eventId.
    """
    creds = ensure_credentials()
    service = build("calendar", "v3", credentials=creds)
    calendar_id = os.getenv("GCAL_CALENDAR_ID", "primary")

    end_dt = start_dt + datetime.timedelta(minutes=duration_min)
    body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": os.getenv("LOCAL_TZ", "UTC")},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": os.getenv("LOCAL_TZ", "UTC")},
        "extendedProperties": {"private": {"notion_page_id": meal_page_id}},
    }
    if description_url:
        body["description"] = description_url

    # search for existing event by private extended property is not directly supported; naive scan recent events
    now = datetime.datetime.utcnow().isoformat() + "Z"
    events = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=250,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    for ev in events.get("items", []):
        ext = ev.get("extendedProperties", {}).get("private", {})
        if ext.get("notion_page_id") == meal_page_id:
            # patch
            eid = ev["id"]
            updated = (
                service.events()
                .patch(calendarId=calendar_id, eventId=eid, body=body)
                .execute()
            )
            return updated["id"]

    created = service.events().insert(calendarId=calendar_id, body=body).execute()
    return created["id"]
