"""Reports router."""

from fastapi import APIRouter, Depends
from sqlmodel import Session
from app.database import get_session
from app.services.progress_report import compute_progress_report

router = APIRouter()


@router.get("/progress")
def get_progress_report(session: Session = Depends(get_session)):
    return compute_progress_report(session)
