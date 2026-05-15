"""Gmail sync endpoints — manual trigger and status check."""

import json
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session, select

from app.database import get_session, engine
from app.models import GmailSyncState

router = APIRouter()


def _run_sync_background():
    with Session(engine) as session:
        from app.services.gmail_sync_service import run_gmail_sync
        run_gmail_sync(session)


@router.post("/sync")
def trigger_sync(session: Session = Depends(get_session)):
    """Manually trigger a Gmail sync cycle (looks back 24 hours)."""
    from app.services.gmail_sync_service import run_gmail_sync
    result = run_gmail_sync(session)
    return result


@router.post("/sync-async")
def trigger_sync_async(background_tasks: BackgroundTasks):
    """Fire-and-forget Gmail sync — returns immediately, runs in background."""
    background_tasks.add_task(_run_sync_background)
    return {"queued": True, "message": "Sync started in background — check /status in 30s"}


@router.post("/reset-token")
def reset_token(session: Session = Depends(get_session)):
    """Force re-seed the Gmail token from GMAIL_TOKEN_B64 env var into the DB."""
    from app.services.gmail_sync_service import _bootstrap_token, _persist_token
    _bootstrap_token(None)   # write env var token to disk (bypasses DB)
    _persist_token(session)  # read disk → write to DB
    return {"ok": True, "message": "Token reseeded from GMAIL_TOKEN_B64 env var"}


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
