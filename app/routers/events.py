"""Events router."""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Event

router = APIRouter()

BOSTON_KEYWORDS = [
    "boston", "cambridge", "somerville", "brookline", "watertown",
    "waltham", "newton", "ma,", "massachusetts", ", ma", "mit",
]

def _is_boston_area(event: Event) -> bool:
    loc = (event.location or "").lower()
    return any(kw in loc for kw in BOSTON_KEYWORDS)

def _days_from_today(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        today = datetime.utcnow().date()
        event_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (event_date - today).days
    except Exception:
        return None

def _enrich(event: Event) -> dict:
    d = event.dict()
    days = _days_from_today(event.date)
    d["days_away"] = days
    d["is_boston_area"] = _is_boston_area(event)
    d["weeks_away"] = round(days / 7, 1) if days is not None else None
    return d


class EventCreate(BaseModel):
    name: str
    date: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    cost: Optional[str] = None
    description: Optional[str] = None
    category: str = "strategic"


@router.get("")
def list_events(
    upcoming_only: bool = True,
    boston_only: bool = False,
    mode: Optional[str] = None,   # "this_week" | "register" | None = all
    session: Session = Depends(get_session),
):
    """
    mode=this_week  → next 7 days, all locations
    mode=register   → 14–90 days out, Boston/Cambridge area only
    default         → all upcoming, sorted by net_score
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    events = session.exec(select(Event)).all()

    if upcoming_only:
        events = [e for e in events if not e.date or e.date >= today]

    if mode == "this_week":
        # 0–7 days; all locations (Boston filter applied in frontend by relevance)
        cutoff = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        events = [e for e in events if e.date and e.date <= cutoff]
        events.sort(key=lambda e: e.date or "")

    elif mode == "register":
        # 8–90 days out; Boston/Cambridge OR strategic category
        min_date = (datetime.utcnow() + timedelta(days=8)).strftime("%Y-%m-%d")
        max_date = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")
        events = [
            e for e in events
            if e.date and min_date <= e.date <= max_date
            and (_is_boston_area(e) or (e.category or "").upper() == "STRATEGIC")
        ]
        events.sort(key=lambda e: e.date or "")

    else:
        if boston_only:
            events = [e for e in events if _is_boston_area(e)]
        events.sort(key=lambda e: -(e.net_score or 0))

    return [_enrich(e) for e in events]


@router.post("")
def add_event(data: EventCreate, session: Session = Depends(get_session)):
    event = Event(**data.dict())
    session.add(event)
    session.commit()
    session.refresh(event)
    return _enrich(event)


@router.get("/this-week-checked")
async def this_week_with_calendar_check(session: Session = Depends(get_session)):
    """
    This week's Boston-area events enriched with Google Calendar presence.
    Checks aldana.santiago@gmail.com primary calendar for matching events.
    """
    from app.services.calendar_sync import get_calendar_events_this_week, check_event_in_calendar

    today = datetime.utcnow().strftime("%Y-%m-%d")
    cutoff = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")

    events = session.exec(select(Event)).all()
    this_week = [e for e in events if e.date and today <= e.date <= cutoff]
    this_week.sort(key=lambda e: e.date or "")

    cal_events = await get_calendar_events_this_week()

    result = []
    for e in this_week:
        enriched = _enrich(e)
        enriched["in_calendar"] = check_event_in_calendar(e.name or "", cal_events)
        result.append(enriched)
    return result


INVITE_ATTENDEES = [
    "saldana@stmaryscu.org",
    "santiago@aidatasolutions.co",
]


@router.post("/add-to-calendar")
async def add_event_to_calendar(event_id: int, session: Session = Depends(get_session)):
    """
    Add a job-search event to Google Calendar and send invites to
    saldana@stmaryscu.org and santiago@aidatasolutions.co.
    """
    event = session.get(Event, event_id)
    if not event:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from app.services.calendar_sync import _get_credentials

        creds_data = _get_credentials()
        if not creds_data:
            # No local OAuth — fall back to MCP-based creation (handled client-side)
            return {"status": "not_configured", "message": "Google Calendar not configured locally"}

        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
        )
        service = build("calendar", "v3", credentials=creds)

        date_str = event.date or datetime.utcnow().strftime("%Y-%m-%d")
        body = {
            "summary": event.name,
            "location": event.location or "",
            "description": (
                f"{event.description or ''}\n\n"
                f"Register: {event.url or ''}\n\n"
                "[Job Search Event]"
            ),
            "start": {"date": date_str},
            "end": {"date": date_str},
            "colorId": "9",  # Blueberry
            "attendees": [{"email": addr} for addr in INVITE_ATTENDEES],
            "guestsCanSeeOtherGuests": False,
        }
        created = service.events().insert(
            calendarId="primary",
            body=body,
            sendUpdates="all",  # sends email invites to attendees
        ).execute()
        return {
            "status": "added",
            "calendar_url": created.get("htmlLink"),
            "invites_sent": INVITE_ATTENDEES,
        }

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{event_id}/meetings")
def update_meetings_booked(
    event_id: int,
    count: int,
    session: Session = Depends(get_session),
):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.meetings_booked = count
    session.add(event)
    session.commit()
    return _enrich(event)


@router.patch("/{event_id}/register")
def mark_registered(
    event_id: int,
    registered: bool = True,
    session: Session = Depends(get_session),
):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.is_registered = registered
    session.add(event)
    session.commit()
    return _enrich(event)
