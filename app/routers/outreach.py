"""Outreach router — log outreach, generate scripts, track 3B7 follow-ups."""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import OutreachRecord, Company, Contact

router = APIRouter()


class OutreachCreate(BaseModel):
    company_id: int
    contact_id: Optional[int] = None
    lead_id: Optional[int] = None
    channel: str = "email"
    subject: Optional[str] = None
    body: Optional[str] = None
    sent_at: Optional[str] = None  # ISO datetime; defaults to now


class OutreachGenerateRequest(BaseModel):
    company_id: int
    contact_id: Optional[int] = None
    lead_id: Optional[int] = None
    context: Optional[str] = None          # free-text: how you met, shared topics, etc.
    hook: Optional[str] = None             # specific angle or topic to lead with
    ask: Optional[str] = None              # what you want from this email
    email_type: str = "cold"               # cold | followup | event_met


@router.get("")
def list_outreach(
    company_id: Optional[int] = None,
    response_status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(OutreachRecord)
    if company_id:
        q = q.where(OutreachRecord.company_id == company_id)
    if response_status:
        q = q.where(OutreachRecord.response_status == response_status)
    records = session.exec(q.order_by(OutreachRecord.sent_at.desc())).all()
    return records


@router.get("/due-today")
def due_today(session: Session = Depends(get_session)):
    """Return outreach records with follow-up due today or overdue."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_3_due <= today,
        )
    ).all()
    return records


@router.post("")
def log_outreach(data: OutreachCreate, session: Session = Depends(get_session)):
    """Log an outreach that was sent (manual entry)."""
    sent_at = data.sent_at or datetime.utcnow().isoformat()
    sent_date = datetime.fromisoformat(sent_at).date()
    follow_up_3 = (sent_date + timedelta(days=3)).isoformat()
    follow_up_7 = (sent_date + timedelta(days=7)).isoformat()

    record = OutreachRecord(
        company_id=data.company_id,
        contact_id=data.contact_id,
        lead_id=data.lead_id,
        channel=data.channel,
        sent_at=sent_at,
        subject=data.subject,
        body=data.body,
        response_status="pending",
        follow_up_3_due=follow_up_3,
        follow_up_7_due=follow_up_7,
    )
    session.add(record)

    # Move company to outreach stage
    if data.company_id:
        company = session.get(Company, data.company_id)
        if company and company.stage in ("pool", "researched"):
            company.stage = "outreach"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    session.commit()
    session.refresh(record)
    return record


@router.post("/generate")
async def generate_outreach(
    req: OutreachGenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate a 6-point outreach email via Claude Opus."""
    company = session.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    contact = session.get(Contact, req.contact_id) if req.contact_id else None

    try:
        from app.services.outreach_generator import generate_6point_email
        result = await generate_6point_email(
            company=company,
            contact=contact,
            context=req.context,
            hook=req.hook,
            ask=req.ask,
            email_type=req.email_type,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{record_id}/response")
def update_response(
    record_id: int,
    response_status: str,
    session: Session = Depends(get_session),
):
    valid = {"pending", "positive", "negative", "ghosted"}
    if response_status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status")

    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    record.response_status = response_status
    record.updated_at = datetime.utcnow().isoformat()

    # Advance company stage on positive response
    if response_status == "positive" and record.company_id:
        company = session.get(Company, record.company_id)
        if company and company.stage == "outreach":
            company.stage = "response"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    session.add(record)
    session.commit()
    return record
