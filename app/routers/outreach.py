"""Outreach router — log outreach, generate scripts, track 3B7 follow-ups."""

from datetime import datetime, timedelta, date
from typing import Optional
import json
import urllib.parse
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


@router.get("/stats")
def get_outreach_stats(session: Session = Depends(get_session)):
    """Compute outreach effectiveness metrics in one pass."""
    records = session.exec(select(OutreachRecord)).all()
    companies = {c.id: c for c in session.exec(select(Company)).all()}

    from datetime import timezone
    now = datetime.utcnow()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    total_sent = len(records)
    sent_last_30d = sum(1 for r in records if r.sent_at and r.sent_at >= thirty_days_ago)

    positive = [r for r in records if r.response_status == "positive"]
    ghosted = [r for r in records if r.response_status == "ghosted"]

    overall_response_rate = round(len(positive) / total_sent, 3) if total_sent else 0.0
    overall_ghosted_pct = round(len(ghosted) / total_sent, 3) if total_sent else 0.0

    # Avg days to positive reply
    days_to_reply = []
    for r in positive:
        if r.sent_at and r.updated_at:
            try:
                sent = datetime.fromisoformat(r.sent_at[:19])
                updated = datetime.fromisoformat(r.updated_at[:19])
                delta = (updated - sent).days
                if delta >= 0:
                    days_to_reply.append(delta)
            except Exception:
                pass
    avg_days_to_positive = round(sum(days_to_reply) / len(days_to_reply), 1) if days_to_reply else None

    # By channel
    channels = ["email", "linkedin", "referral"]
    by_channel = {}
    for ch in channels:
        ch_records = [r for r in records if r.channel == ch]
        ch_positive = sum(1 for r in ch_records if r.response_status == "positive")
        ch_ghosted = sum(1 for r in ch_records if r.response_status == "ghosted")
        n = len(ch_records)
        by_channel[ch] = {
            "sent": n,
            "response_rate": round(ch_positive / n, 3) if n else 0.0,
            "ghosted_pct": round(ch_ghosted / n, 3) if n else 0.0,
        }

    # Best channel (≥3 records, highest response rate)
    best_channel = None
    best_rate = -1.0
    for ch, stats in by_channel.items():
        if stats["sent"] >= 3 and stats["response_rate"] > best_rate:
            best_rate = stats["response_rate"]
            best_channel = ch

    # By funding stage
    by_funding_stage = {}
    for r in records:
        company = companies.get(r.company_id)
        stage = (company.funding_stage if company else None) or "unknown"
        if stage not in by_funding_stage:
            by_funding_stage[stage] = {"sent": 0, "positive": 0}
        by_funding_stage[stage]["sent"] += 1
        if r.response_status == "positive":
            by_funding_stage[stage]["positive"] += 1
    for stage, data in by_funding_stage.items():
        n = data["sent"]
        data["response_rate"] = round(data["positive"] / n, 3) if n else 0.0

    return {
        "total_sent": total_sent,
        "sent_last_30d": sent_last_30d,
        "overall_response_rate": overall_response_rate,
        "overall_ghosted_pct": overall_ghosted_pct,
        "avg_days_to_positive": avg_days_to_positive,
        "best_channel": best_channel,
        "by_channel": by_channel,
        "by_funding_stage": by_funding_stage,
    }


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
        if contact and contact.outreach_status == "none":
            contact.outreach_status = "drafted"
            contact.updated_at = datetime.utcnow().isoformat()
            session.add(contact)
            session.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{record_id}")
def delete_outreach(record_id: int, session: Session = Depends(get_session)):
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(record)
    session.commit()
    return {"ok": True}


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


class FollowUpDraftRequest(BaseModel):
    followup_day: int  # 3 or 7
    language: str = "en"  # "en" or "es"


class SendFollowUpRequest(BaseModel):
    subject: str
    body: str
    followup_day: int  # 3 or 7


@router.post("/{record_id}/draft-followup")
async def draft_followup(
    record_id: int,
    req: FollowUpDraftRequest,
    session: Session = Depends(get_session),
):
    """
    Generate a template-based follow-up email (no API cost).
    Returns: {subject, body, stage, template_used: True, has_conversation_context: bool}

    Optional query param: ?enhance_with_context=true to refine with Claude Opus (API cost).
    """
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    company = session.get(Company, record.company_id) if record.company_id else None
    contact = session.get(Contact, record.contact_id) if record.contact_id else None

    # Map followup_day to stage
    stage = "day_3" if req.followup_day == 3 else "day_7"

    # Build outreach record dict for template function
    from datetime import datetime, date
    outreach_dict = {
        "company": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "there",
        "contact_role": contact.title if contact else "Professional",
        "sent_date": record.sent_at or datetime.utcnow().isoformat(),
        "generated_subject": record.subject or "our conversation",
        "notes": record.notes or "",
    }

    # Generate template-based draft (no API call)
    from app.services.outreach_generator import draft_followup_from_template
    draft = draft_followup_from_template(stage, outreach_dict)

    if "error" in draft:
        raise HTTPException(status_code=400, detail=draft["error"])

    # Check if conversation history exists (for UI indication)
    from skills.outreach_tracker import get_conversation_history
    history = get_conversation_history(record_id) if record_id else []

    return {
        "subject": draft.get("subject"),
        "body": draft.get("body"),
        "stage": draft.get("stage"),
        "template_used": draft.get("template_used", True),
        "has_conversation_context": len(history) > 0,
        "followup_day": req.followup_day,
        "company_name": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "Unknown",
        "reasoning": draft.get("reasoning", "Generated from template"),
    }


class EnhanceWithContextRequest(BaseModel):
    subject: str  # Template-generated subject
    body: str  # Template-generated body
    stage: str  # "day_3" | "day_7" | "harvest"


@router.post("/{record_id}/enhance-with-context")
async def enhance_with_context(
    record_id: int,
    req: EnhanceWithContextRequest,
    session: Session = Depends(get_session),
):
    """
    Optional on-demand enhancement: refine a template draft using conversation context.
    Calls Claude Opus with full conversation history (costs API token).
    Returns: {subject, body, reasoning, enhanced: True}
    """
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Fetch conversation history
    from skills.outreach_tracker import get_conversation_history
    history = get_conversation_history(record_id)

    if not history:
        raise HTTPException(
            status_code=400,
            detail="No conversation history found for this record. Enhancement requires prior exchange.",
        )

    # Call enhancement function
    from app.services.outreach_generator import enhance_draft_with_context
    enhanced = await enhance_draft_with_context(
        req.subject,
        req.body,
        history,
        stage=req.stage,
    )

    return {
        "subject": enhanced.get("subject"),
        "body": enhanced.get("body"),
        "reasoning": enhanced.get("reasoning"),
        "enhanced": enhanced.get("enhanced", False),
    }


@router.post("/{record_id}/send-followup")
def send_followup(
    record_id: int,
    req: SendFollowUpRequest,
    session: Session = Depends(get_session),
):
    """Mark follow-up as sent, log new outreach record, return mailto link."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    contact = session.get(Contact, record.contact_id) if record.contact_id else None
    to_email = (contact.email or "") if contact else ""

    # Build mailto link — must use %20 (RFC 3986), not + (form encoding)
    subject_enc = urllib.parse.quote(req.subject or "", safe="")
    body_enc = urllib.parse.quote(req.body or "", safe="")
    to_part = f"mailto:{urllib.parse.quote(to_email, safe='@.')}" if to_email else "mailto:"
    mailto_url = f"{to_part}?subject={subject_enc}&body={body_enc}"

    # Mark the appropriate follow-up sent and reset Day 7 from actual send date
    today = date.today()
    if req.followup_day == 3:
        record.follow_up_3_sent = True
        record.follow_up_7_due = (today + timedelta(days=4)).isoformat()
    else:
        record.follow_up_7_sent = True
    record.updated_at = datetime.utcnow().isoformat()

    session.add(record)
    session.commit()

    return {"ok": True, "mailto_url": mailto_url, "to_email": to_email or None}


@router.post("/{record_id}/skip")
def skip_outreach(record_id: int, session: Session = Depends(get_session)):
    """Skip all remaining follow-ups (mark as sent, set response to ghosted)."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    record.follow_up_3_sent = True
    record.follow_up_7_sent = True
    record.response_status = "ghosted"
    record.updated_at = datetime.utcnow().isoformat()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
