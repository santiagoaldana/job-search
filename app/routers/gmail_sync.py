"""Gmail sync endpoints — manual trigger and status check."""

import json
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import GmailSyncState

router = APIRouter()


@router.post("/sync")
def trigger_sync(session: Session = Depends(get_session)):
    """Manually trigger a Gmail sync cycle (looks back 24 hours)."""
    from app.services.gmail_sync_service import run_gmail_sync
    result = run_gmail_sync(session)
    return result


@router.get("/status")
def sync_status(session: Session = Depends(get_session)):
    """Return last sync time and summary."""
    state = session.exec(select(GmailSyncState)).first()
    if not state:
        return {"synced": False, "last_poll_at": None, "summary": {}}
    return {
        "synced": True,
        "account": state.account_email,
        "last_poll_at": state.last_poll_at,
        "summary": json.loads(state.last_sync_summary or "{}"),
    }
