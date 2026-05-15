"""Outreach router — log outreach, generate scripts, track 3B7 follow-ups."""

from datetime import datetime, timedelta, date
from typing import Optional
import json
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel


def add_business_days(start: date, days: int) -> date:
    """Return a date that is `days` business days after `start`, skipping weekends."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 … Fri=4
            added += 1
    return current

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
    outreach_message: Optional[str] = None
    sent_at: Optional[str] = None  # ISO datetime; defaults to now
    contact_name_raw: Optional[str] = None  # fallback when contact not yet in DB


class OutreachGenerateRequest(BaseModel):
    company_id: int
    contact_id: Optional[int] = None
    lead_id: Optional[int] = None
    context: Optional[str] = None
    hook: Optional[str] = None
    ask: Optional[str] = None
    email_type: str = "cold"
    prior_message: Optional[str] = None
    # Pre-generated content from Claude (when provided, saves draft directly)
    subject: Optional[str] = None
    body: Optional[str] = None
    word_count: Optional[int] = None
    rationale: Optional[str] = None


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
    follow_up_3 = add_business_days(sent_date, 3).isoformat()
    follow_up_7 = add_business_days(sent_date, 7).isoformat()

    notes = None
    if not data.contact_id and data.contact_name_raw:
        notes = f"contact:{data.contact_name_raw}"

    # Inherit company from contact if not explicitly provided
    company_id = data.company_id
    if not company_id and data.contact_id:
        linked_contact = session.get(Contact, data.contact_id)
        if linked_contact and linked_contact.company_id:
            company_id = linked_contact.company_id

    # If an earlier outreach exists for this contact, carry its canonical message forward
    prior_message = None
    if data.contact_id:
        prior = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == data.contact_id)
            .where(OutreachRecord.outreach_message != None)
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if prior:
            prior_message = prior.outreach_message

    record = OutreachRecord(
        company_id=company_id,
        contact_id=data.contact_id,
        lead_id=data.lead_id,
        channel=data.channel,
        sent_at=sent_at,
        subject=data.subject,
        body=data.body,
        outreach_message=data.outreach_message or data.body or prior_message,
        response_status="pending",
        follow_up_3_due=follow_up_3,
        follow_up_7_due=follow_up_7,
        notes=notes,
    )
    session.add(record)

    # Move company to outreach stage
    if company_id:
        company = session.get(Company, company_id)
        if company and company.stage in ("pool", "researched"):
            company.stage = "outreach"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    # Update contact outreach status
    if data.contact_id:
        contact = session.get(Contact, data.contact_id)
        if contact and contact.outreach_status == "none":
            contact.outreach_status = "drafted"
            session.add(contact)

    session.commit()
    session.refresh(record)

    # Store original outreach message in conversation history
    from app.models import ConversationMessage
    try:
        contact = session.get(Contact, data.contact_id) if data.contact_id else None
        outreach_msg = ConversationMessage(
            outreach_record_id=record.id,
            message_date=sent_at,
            from_email="santiago@aidatasolutions.co",
            from_name="Santiago Aldana",
            to_email=contact.email if contact else "",
            subject=data.subject,
            body_full=data.body or "",
            message_type="outreach",
        )
        session.add(outreach_msg)
        session.commit()
    except Exception:
        pass  # Non-critical; conversation history still works

    return record


@router.post("/generate")
async def generate_outreach(
    req: OutreachGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    If subject+body are provided (pre-generated by Claude): save the draft and return it.
    Otherwise: assemble and return outreach context for Claude to generate from.
    """
    company = session.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    contact = session.get(Contact, req.contact_id) if req.contact_id else None

    # Pre-generated path: Claude already wrote the draft, just persist and return
    if req.subject and req.body:
        if contact and contact.outreach_status == "none":
            contact.outreach_status = "drafted"
            session.add(contact)
            session.commit()
        return {
            "subject": req.subject,
            "body": req.body,
            "word_count": req.word_count or len(req.body.split()),
            "rationale": req.rationale,
        }

    # Context-only path: assemble context for Claude to generate from
    from app.services.outreach_generator import build_outreach_context

    prior_message = req.prior_message
    if not prior_message and req.contact_id:
        prior = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == req.contact_id)
            .where(OutreachRecord.outreach_message != None)
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if prior:
            prior_message = prior.outreach_message

    return build_outreach_context(
        company=company,
        contact=contact,
        email_type=req.email_type,
        context=req.context,
        hook=req.hook,
        ask=req.ask,
        prior_message=prior_message,
    )


class OutreachSaveDraftRequest(BaseModel):
    company_id: int
    contact_id: Optional[int] = None
    subject: str
    body: str
    email_type: str = "cold"
    rationale: Optional[str] = None
    word_count: Optional[int] = None


@router.post("/save-draft")
def save_outreach_draft(req: OutreachSaveDraftRequest, session: Session = Depends(get_session)):
    """Persist a pre-generated outreach draft from the MCP layer. No OutreachRecord created yet."""
    company = session.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    contact = session.get(Contact, req.contact_id) if req.contact_id else None
    if contact and contact.outreach_status == "none":
        contact.outreach_status = "drafted"
        session.add(contact)
        session.commit()
    return {
        "subject": req.subject,
        "body": req.body,
        "email_type": req.email_type,
        "word_count": req.word_count or len(req.body.split()),
        "rationale": req.rationale,
        "company_id": req.company_id,
        "contact_id": req.contact_id,
    }


@router.delete("/{record_id}")
def delete_outreach(record_id: int, session: Session = Depends(get_session)):
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(record)
    session.commit()
    return {"ok": True}


class OutreachUpdate(BaseModel):
    follow_up_3_due: Optional[str] = None
    follow_up_7_due: Optional[str] = None
    follow_up_3_sent: Optional[bool] = None
    follow_up_7_sent: Optional[bool] = None
    notes: Optional[str] = None
    linkedin_accepted: Optional[bool] = None
    contact_id: Optional[int] = None
    outreach_message: Optional[str] = None


@router.patch("/{record_id}")
def patch_outreach(record_id: int, data: OutreachUpdate, session: Session = Depends(get_session)):
    """Patch arbitrary fields on an outreach record."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    if data.follow_up_3_due is not None:
        record.follow_up_3_due = data.follow_up_3_due
    if data.follow_up_7_due is not None:
        record.follow_up_7_due = data.follow_up_7_due
    if data.follow_up_3_sent is not None:
        record.follow_up_3_sent = data.follow_up_3_sent
    if data.follow_up_7_sent is not None:
        record.follow_up_7_sent = data.follow_up_7_sent
    if data.notes is not None:
        record.notes = data.notes
    if data.linkedin_accepted is not None:
        record.linkedin_accepted = data.linkedin_accepted
    if data.contact_id is not None:
        record.contact_id = data.contact_id
    if data.outreach_message is not None:
        record.outreach_message = data.outreach_message
    record.updated_at = datetime.utcnow().isoformat()
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


class ResponseUpdate(BaseModel):
    response_status: str
    notes: Optional[str] = None


@router.patch("/{record_id}/response")
def update_response(
    record_id: int,
    data: ResponseUpdate,
    session: Session = Depends(get_session),
):
    valid = {"pending", "positive", "negative", "ghosted"}
    if data.response_status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status")

    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    record.response_status = data.response_status
    record.updated_at = datetime.utcnow().isoformat()

    if data.notes is not None:
        record.notes = data.notes

    # Reset follow-up counter from today when a reply is received
    if data.response_status == "positive":
        today = datetime.utcnow().date()
        record.follow_up_3_due = add_business_days(today, 3).isoformat()
        record.follow_up_7_due = add_business_days(today, 7).isoformat()
        record.follow_up_3_sent = False
        record.follow_up_7_sent = False

    # Advance company stage on positive response
    if data.response_status == "positive" and record.company_id:
        company = session.get(Company, record.company_id)
        if company and company.stage == "outreach":
            company.stage = "response"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    session.add(record)
    session.commit()
    return record


class ConfirmEscalationRequest(BaseModel):
    contact_id: Optional[int] = None
    guessed_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class FollowUpDraftRequest(BaseModel):
    followup_day: int  # 3 or 7
    language: str = "en"  # "en" or "es"


class SendFollowUpRequest(BaseModel):
    subject: str
    body: str
    followup_day: int  # 3 or 7


class MarkFollowUpSentRequest(BaseModel):
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
    import re as _re
    raw_subject = record.subject or ""
    # Strip em/en dashes and hyphens; drop subjects that are contact-lookup artifacts
    clean_subject = _re.sub(r"[–—\-]+", " ", raw_subject).strip()
    if not clean_subject or "LinkedIn connection" in clean_subject:
        clean_subject = f"{company.name} quick question" if company else "our conversation"
    outreach_dict = {
        "company": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "there",
        "contact_role": contact.title if contact else "Professional",
        "sent_date": record.sent_at or datetime.utcnow().isoformat(),
        "generated_subject": clean_subject,
        "notes": record.notes or "",
    }

    # Generate template-based draft (no API call)
    from app.services.outreach_generator import draft_followup_from_template
    draft = draft_followup_from_template(stage, outreach_dict, language=req.language)

    if "error" in draft:
        raise HTTPException(status_code=400, detail=draft["error"])

    # Fetch conversation history (zero API cost — just database read)
    from skills.outreach_tracker import get_conversation_history
    history = get_conversation_history(record_id) if record_id else []
    print(f"[DEBUG] draft_followup: record_id={record_id}, history_count={len(history)}", flush=True)

    # Format conversation for display
    conversation_text = ""
    if history:
        print(f"[DEBUG] Formatting {len(history)} messages into conversation_text", flush=True)
        for msg in reversed(history[-5:]):  # Last 5 messages, reversed for chronological order
            conversation_text += f"\n{'='*60}\n"
            conversation_text += f"From: {msg.get('from_name', msg.get('from_email', 'Unknown'))}\n"
            conversation_text += f"Date: {msg.get('date', 'Unknown')}\n"
            conversation_text += f"Subject: {msg.get('subject', '(no subject)')}\n"
            conversation_text += f"---\n{msg.get('body_preview', '')}\n"
        print(f"[DEBUG] conversation_text length: {len(conversation_text)}", flush=True)
    else:
        print(f"[DEBUG] No history returned, conversation_text will be empty", flush=True)

    return {
        "subject": draft.get("subject"),
        "body": draft.get("body"),
        "stage": draft.get("stage"),
        "template_used": draft.get("template_used", True),
        "has_conversation_context": len(history) > 0,
        "conversation_history": history,  # Full structured history for UI to display
        "conversation_text": conversation_text,  # Plain text version for easy reading
        "followup_day": req.followup_day,
        "company_name": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "Unknown",
        "reasoning": draft.get("reasoning", "Generated from template"),
    }


class EnhanceWithContextRequest(BaseModel):
    subject: str
    body: str
    stage: str  # "day_3" | "day_7" | "harvest"


@router.post("/{record_id}/conversation-context")
async def get_conversation_context(
    record_id: int,
    req: EnhanceWithContextRequest,
    session: Session = Depends(get_session),
):
    """
    Return conversation history + template draft so Claude can generate an enhanced version.
    No AI call — data only.
    """
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    from skills.outreach_tracker import get_conversation_history
    history = get_conversation_history(record_id)

    if not history:
        raise HTTPException(
            status_code=400,
            detail="No conversation history found for this record.",
        )

    return {
        "record_id": record_id,
        "stage": req.stage,
        "draft_subject": req.subject,
        "draft_body": req.body,
        "conversation_history": history,
        "generation_instructions": (
            "Refine the draft to reference specific points from the conversation above. "
            "Maintain warm, conversational tone. Keep body ≤100 words. "
            "Do NOT use corporate jargon or 'synergy', 'circle back', 'pick your brain'. "
            "Do NOT add a signature block. Return JSON: "
            '{"subject": "...", "body": "...", "reasoning": "why this version is better"}'
        ),
    }


EXPERTISE_MAP = [
    (["payment", "acquiring", "issuing", "card", "transaction"], "payments"),
    (["baas", "banking as a service", "embedded banking", "embedded finance"], "BaaS"),
    (["identity", "fraud", "kyc", "verification", "authentication"], "digital identity and fraud prevention"),
    (["ai", "agentic", "llm", "machine learning", "automation"], "agentic AI"),
    (["stablecoin", "crypto", "blockchain", "web3", "defi"], "stablecoins and digital assets"),
    (["credit union", "cuso", "community bank"], "credit union fintech partnerships"),
    (["marketing", "crm", "lifecycle", "retention", "email"], "AI-driven marketing"),
    (["people", "hr", "human resources", "talent", "recruiting", "culture", "chief people", "chro", "workforce"], "building high-performance teams in fintech"),
    (["product", "chief product", "head of product", "vp product"], "product strategy in fintech"),
    (["banking", "fintech", "financial"], "financial technology"),
]


def _derive_expertise(contact, company) -> str:
    search = ((contact.title or "") + " " + (company.name if company else "")).lower()
    for keywords, label in EXPERTISE_MAP:
        if any(k in search for k in keywords):
            return label
    return "fintech and payments"


@router.post("/{record_id}/draft-template")
def draft_template(
    record_id: int,
    followup_type: str = "escalation",
    contact_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Return a Dalton-compliant personalized email draft with no Claude API call."""
    from app.models import OutreachRecord, Contact, Company
    from app.services.email_finder import determine_next_step as _contact_next_step

    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # contact_id param overrides record.contact_id to handle stale/wrong associations
    resolved_contact_id = contact_id if contact_id is not None else record.contact_id
    contact = session.get(Contact, resolved_contact_id) if resolved_contact_id else None
    company = session.get(Company, record.company_id) if record.company_id else None

    first = (contact.name or "").split()[0] if contact else "there"
    company_name = company.name if company else "your company"

    if followup_type == "escalation":
        expertise = _derive_expertise(contact, company)
        role = contact.title or "role"
        is_mit = getattr(contact, "is_mit_alum", None) if contact else None

        subject = f"Quick question about {company_name}"

        if is_mit:
            opener = "I am a fellow MIT Sloan alum."
        else:
            opener = f"I noticed we have a common interest in {expertise}."

        body = (
            f"Hi {first},\n\n"
            f"{opener} I was wondering if you have some time to tell me about your "
            f"{role} role at {company_name}? Your insights would be greatly appreciated "
            f"because I'm trying to learn more about {expertise}. "
            f"Worth exchanging notes?"
        )

    elif followup_type == "day3":
        subject = f"{company_name} — still curious"
        body = (
            f"Hi {first},\n\n"
            f"Just bumping this up in case it got buried. "
            f"Still curious about your perspective on this.\n\n"
            f"Worth a quick note back?"
        )
    elif followup_type == "day7":
        subject = f"Closing the loop — {company_name}"
        body = (
            f"Hi {first},\n\n"
            f"Wanted to close the loop on my earlier note. "
            f"If the timing isn't right, no worries at all. Happy to reconnect down the road."
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid followup_type")

    guessed_email = None
    if contact and contact.email:
        guessed_email = contact.email
    elif contact and company:
        ns = _contact_next_step(contact, company)
        guessed_email = ns.get("guessed_email")

    # Fetch prior canonical message so UI can show it as "sent before" reference
    prior_message = None
    if record.outreach_message:
        prior_message = record.outreach_message
    elif record.contact_id:
        prior = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == record.contact_id)
            .where(OutreachRecord.outreach_message != None)
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if prior:
            prior_message = prior.outreach_message

    return {"subject": subject, "body": body, "guessed_email": guessed_email, "prior_message": prior_message}


@router.post("/{record_id}/confirm-escalation")
def confirm_escalation(
    record_id: int,
    req: ConfirmEscalationRequest,
    session: Session = Depends(get_session),
):
    """
    Called when user confirms sending the LinkedIn escalation email.
    Creates a new email OutreachRecord to start the 3B7 email clock,
    stores the guessed email on the contact, and marks the LinkedIn record
    follow_up_3_sent so it stops appearing in the Daily Brief.
    """
    linkedin_record = session.get(OutreachRecord, record_id)
    if not linkedin_record:
        raise HTTPException(status_code=404, detail="Record not found")

    today = datetime.utcnow()

    # Store guessed email on contact so Gmail sync can match the bounce
    if req.contact_id and req.guessed_email:
        contact = session.get(Contact, req.contact_id)
        if contact and not contact.email:
            contact.email = req.guessed_email
            contact.email_guessed = True
            session.add(contact)

    # Only create a new email OutreachRecord if one doesn't already exist for this contact
    # (prevents duplicates when email was already logged via MCP before clicking "Yes, sent")
    existing_email = None
    if linkedin_record.contact_id:
        existing_email = session.exec(
            select(OutreachRecord).where(
                OutreachRecord.contact_id == linkedin_record.contact_id,
                OutreachRecord.channel == "email",
            )
        ).first()

    if not existing_email:
        email_record = OutreachRecord(
            company_id=linkedin_record.company_id,
            contact_id=linkedin_record.contact_id,
            channel="email",
            subject=req.subject,
            body=req.body,
            sent_at=today.isoformat(),
            response_status="pending",
            follow_up_3_due=add_business_days(today.date(), 3).isoformat(),
            follow_up_7_due=add_business_days(today.date(), 7).isoformat(),
            follow_up_3_sent=False,
            follow_up_7_sent=False,
        )
        session.add(email_record)
    else:
        email_record = existing_email

    # Mark LinkedIn record so it stops showing in Daily Brief
    linkedin_record.follow_up_3_sent = True
    linkedin_record.updated_at = today.isoformat()
    session.add(linkedin_record)

    session.commit()
    session.refresh(email_record)
    return {"ok": True, "email_record_id": email_record.id}


@router.post("/{record_id}/build-mailto")
def build_mailto(
    record_id: int,
    req: SendFollowUpRequest,
    session: Session = Depends(get_session),
):
    """Build and return a mailto URL without marking the follow-up as sent."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    contact = session.get(Contact, record.contact_id) if record.contact_id else None
    to_email = (contact.email or "") if contact else ""

    subject_enc = urllib.parse.quote(req.subject or "", safe="")
    body_enc = urllib.parse.quote(req.body or "", safe="")
    to_part = f"mailto:{urllib.parse.quote(to_email, safe='@.')}" if to_email else "mailto:"
    mailto_url = f"{to_part}?subject={subject_enc}&body={body_enc}"

    return {"mailto_url": mailto_url, "to_email": to_email or None}


@router.post("/{record_id}/mark-followup-sent")
def mark_followup_sent(
    record_id: int,
    req: MarkFollowUpSentRequest,
    session: Session = Depends(get_session),
):
    """Mark a follow-up as sent after user confirms they actually sent it."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    today = date.today()
    if req.followup_day == 3:
        record.follow_up_3_sent = True
        record.follow_up_7_due = add_business_days(today, 4).isoformat()
    else:
        record.follow_up_7_sent = True
    record.updated_at = datetime.utcnow().isoformat()

    session.add(record)
    session.commit()

    return {"ok": True}


@router.post("/{record_id}/send-followup")
def send_followup(
    record_id: int,
    req: SendFollowUpRequest,
    session: Session = Depends(get_session),
):
    """Legacy: build mailto AND mark as sent in one step. Kept for backwards compatibility."""
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    contact = session.get(Contact, record.contact_id) if record.contact_id else None
    to_email = (contact.email or "") if contact else ""

    subject_enc = urllib.parse.quote(req.subject or "", safe="")
    body_enc = urllib.parse.quote(req.body or "", safe="")
    to_part = f"mailto:{urllib.parse.quote(to_email, safe='@.')}" if to_email else "mailto:"
    mailto_url = f"{to_part}?subject={subject_enc}&body={body_enc}"

    today = date.today()
    if req.followup_day == 3:
        record.follow_up_3_sent = True
        record.follow_up_7_due = add_business_days(today, 4).isoformat()
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
