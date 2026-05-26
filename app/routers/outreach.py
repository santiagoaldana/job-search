"""Outreach router — log outreach, generate scripts, track 3B7 follow-ups."""

from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Optional
import json
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

_EASTERN = ZoneInfo("America/New_York")

def _today_eastern() -> str:
    return datetime.now(_EASTERN).strftime("%Y-%m-%d")

def _today_eastern_date() -> date:
    return datetime.now(_EASTERN).date()


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
    today = _today_eastern()
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
    sent_at = data.sent_at or datetime.now(_EASTERN).isoformat()
    sent_date = datetime.fromisoformat(sent_at[:19]).date()
    follow_up_3 = add_business_days(sent_date, 3).isoformat()
    follow_up_7 = add_business_days(sent_date, 7).isoformat()

    # Auto-resolve contact_id by name when not explicitly provided
    resolved_contact_id = data.contact_id
    if not resolved_contact_id and data.contact_name_raw:
        q = select(Contact).where(Contact.name == data.contact_name_raw)
        if data.company_id:
            q = q.where(Contact.company_id == data.company_id)
        matched = session.exec(q).first()
        if matched:
            resolved_contact_id = matched.id

    notes = None
    if not resolved_contact_id and data.contact_name_raw:
        notes = f"contact:{data.contact_name_raw}"

    # Inherit company from contact if not explicitly provided
    company_id = data.company_id
    if not company_id and resolved_contact_id:
        linked_contact = session.get(Contact, resolved_contact_id)
        if linked_contact and linked_contact.company_id:
            company_id = linked_contact.company_id

    # If an earlier outreach exists for this contact, carry its canonical message forward
    prior_message = None
    if resolved_contact_id:
        prior = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == resolved_contact_id)
            .where(OutreachRecord.outreach_message != None)
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if prior:
            prior_message = prior.outreach_message

    record = OutreachRecord(
        company_id=company_id,
        contact_id=resolved_contact_id,
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

    # Context-only path: template-based draft (no API call)
    from app.services.outreach_generator import draft_initial_outreach_from_template

    result = draft_initial_outreach_from_template(
        company=company,
        contact=contact,
        email_type=req.email_type,
        context=req.context,
        hook=req.hook,
        ask=req.ask,
    )

    if contact and contact.outreach_status == "none":
        contact.outreach_status = "drafted"
        session.add(contact)
        session.commit()

    return {
        "subject": result["subject"],
        "body": result["body"],
        "word_count": result["word_count"],
        "rationale": result["rationale"],
    }


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
    escalation_snooze_until: Optional[str] = None
    escalation_channel: Optional[str] = None


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
    if data.escalation_snooze_until is not None:
        record.escalation_snooze_until = data.escalation_snooze_until
    if data.escalation_channel is not None:
        record.escalation_channel = data.escalation_channel
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
        today = _today_eastern_date()
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
    new_element: Optional[str] = None  # MSG-3: user-edited suggestion for the bump


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
    if req.followup_day == 0:
        stage = "post_meeting"
    elif req.followup_day == -1:
        stage = "post_meeting_2"
    elif req.followup_day == 3:
        stage = "day_3"
    else:
        stage = "day_7"

    # Build outreach record dict for template function
    from datetime import datetime, date
    import re as _re
    raw_subject = record.subject or ""
    # Strip em/en dashes and hyphens; drop subjects that are contact-lookup artifacts
    clean_subject = _re.sub(r"[–—\-]+", " ", raw_subject).strip()
    if not clean_subject or "LinkedIn connection" in clean_subject or "logged via MCP" in clean_subject.lower():
        clean_subject = f"{company.name} quick question" if company else "our conversation"
    outreach_dict = {
        "company": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "there",
        "contact_role": contact.title if contact else "Professional",
        "sent_date": record.sent_at or datetime.utcnow().isoformat(),
        "generated_subject": clean_subject,
        "notes": record.notes or "",
    }

    # Generate template-based draft as baseline (no API call)
    from app.services.outreach_generator import (
        draft_followup_from_template, generate_bump_draft, generate_close_draft,
    )
    draft = draft_followup_from_template(stage, outreach_dict, language=req.language)

    if "error" in draft:
        raise HTTPException(status_code=400, detail=draft["error"])

    ai_reasoning = None

    # MSG-3: AI bump when new_element is provided
    if stage == "day_3" and req.new_element and req.new_element.strip():
        original_body = record.outreach_message or record.body or ""
        contact_name = contact.name if contact else "there"
        contact_title = contact.title or ""
        company_name_str = company.name if company else "Unknown"
        ai_result = await generate_bump_draft(
            contact_name, contact_title, company_name_str,
            original_body, req.new_element.strip(),
        )
        if ai_result:
            draft["body"] = ai_result["body"]
            draft["template_used"] = False
            ai_reasoning = ai_result.get("reasoning")

    # MSG-4: AI close always
    elif stage == "day_7":
        original_body = record.outreach_message or record.body or ""
        contact_name = contact.name if contact else "there"
        contact_title = contact.title or ""
        company_name_str = company.name if company else "Unknown"
        ai_result = await generate_close_draft(
            contact_name, contact_title, company_name_str, original_body,
        )
        if ai_result:
            draft["body"] = ai_result["body"]
            draft["template_used"] = False
            ai_reasoning = ai_result.get("reasoning")

    # Fetch conversation history (zero API cost — just database read)
    from skills.outreach_tracker import get_conversation_history
    history = get_conversation_history(record_id) if record_id else []

    # Format conversation for display
    conversation_text = ""
    if history:
        for msg in reversed(history[-5:]):
            conversation_text += f"\n{'='*60}\n"
            conversation_text += f"From: {msg.get('from_name', msg.get('from_email', 'Unknown'))}\n"
            conversation_text += f"Date: {msg.get('date', 'Unknown')}\n"
            conversation_text += f"Subject: {msg.get('subject', '(no subject)')}\n"
            conversation_text += f"---\n{msg.get('body_preview', '')}\n"

    return {
        "subject": draft.get("subject"),
        "body": draft.get("body"),
        "stage": draft.get("stage"),
        "template_used": draft.get("template_used", True),
        "has_conversation_context": len(history) > 0,
        "conversation_history": history,
        "conversation_text": conversation_text,
        "followup_day": req.followup_day,
        "company_name": company.name if company else "Unknown",
        "contact_name": contact.name if contact else "Unknown",
        "reasoning": ai_reasoning or draft.get("reasoning", "Generated from template"),
    }


@router.get("/{record_id}/suggest-bump-element")
async def suggest_bump_element_endpoint(
    record_id: int,
    session: Session = Depends(get_session),
):
    """
    Generate a one-sentence suggested new element for the Day 3 bump.
    Fast Haiku call — pre-fills the UI input before Santiago edits it.
    """
    record = session.get(OutreachRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    company = session.get(Company, record.company_id) if record.company_id else None
    original_body = record.outreach_message or record.body or ""
    intel_summary = (company.intel_summary or "") if company else ""

    from app.services.outreach_generator import suggest_bump_element
    suggestion = await suggest_bump_element(original_body, intel_summary)
    return {"suggestion": suggestion}


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

    santiago_emails = {"santiago@aidatasolutions.co", "aldana.santiago@gmail.com"}
    has_inbound_reply = any(
        (msg.get("from_email") or "").lower() not in santiago_emails
        for msg in history
    )

    if has_inbound_reply:
        generation_instructions = (
            "You are helping Santiago Aldana, an executive with 20+ years in FinTech, payments, "
            "digital identity and LATAM markets, currently Chief Product Solutions Officer at SMCU "
            "(number one SBA credit union lender in Massachusetts). "
            "He is actively searching for C-suite or SVP roles at companies in payments infrastructure, "
            "BaaS, embedded banking, agentic AI, and digital identity. "
            "Companies he is actively connecting with include Infinant, Firmly, Grasshopper Bank, Synctera, and Sardine. "
            "\n\n"
            "Read the conversation history above carefully. Then rewrite the draft to:\n"
            "1. Reference something specific from the prior exchange, not generically.\n"
            "2. If the prior thread involved a referral or closed process, acknowledge its outcome warmly.\n"
            "3. Update the contact on Santiago's current search focus if it adds value.\n"
            "4. End with a light specific ask or offer. Never use 'pick your brain' or 'circle back'.\n"
            "5. Never use em dashes, en dashes, or hyphens as punctuation.\n"
            "Keep body under 100 words. Do NOT add a signature block. "
            'Return JSON: {"subject": "...", "body": "...", "reasoning": "why this version is better"}'
        )
    else:
        generation_instructions = (
            "Refine the draft using the Dalton method: lead with a specific fact about the recipient "
            "or their company, make it about them not Santiago, end with a single light ask. "
            "Maintain warm conversational tone. Keep body under 80 words. "
            "Do NOT use corporate jargon, 'synergy', 'circle back', or 'pick your brain'. "
            "Never use em dashes, en dashes, or hyphens as punctuation. "
            "Do NOT add a signature block. "
            'Return JSON: {"subject": "...", "body": "...", "reasoning": "why this version is better"}'
        )

    return {
        "record_id": record_id,
        "stage": req.stage,
        "draft_subject": req.subject,
        "draft_body": req.body,
        "conversation_history": history,
        "generation_instructions": generation_instructions,
    }


EXPERTISE_MAP = [
    (["payment", "acquiring", "issuing", "card", "transaction"], "payments"),
    (["baas", "banking as a service", "embedded banking", "embedded finance"], "BaaS"),
    (["identity", "fraud", "kyc", "verification", "authentication"], "digital identity and fraud prevention"),
    (["ai", "agentic", "llm", "machine learning", "automation"], "agentic AI"),
    (["stablecoin", "crypto", "blockchain", "web3", "defi"], "stablecoins and digital assets"),
    (["credit union", "cuso", "community bank"], "credit union fintech partnerships"),
    (["marketing", "crm", "lifecycle", "retention", "email", "klaviyo", "martech"], "AI-driven marketing"),
    (["people", "hr", "human resources", "talent", "recruiting", "culture", "chief people", "chro", "workforce"], "building high-performance teams in fintech"),
    (["product", "chief product", "head of product", "vp product"], "product strategy in fintech"),
    (["venture", "vc ", "investor", "investment", "portfolio", "fund", "general partner"], "fintech venture investing"),
    (["strategy", "creation strategy", "growth", "biz dev", "business development", "partnerships"], "fintech growth and strategy"),
    (["banking", "fintech", "financial"], "financial technology"),
]


_EXPERTISE_DEFAULT = "fintech and payments"


def _derive_expertise(contact, company) -> str:
    search = ((contact.title or "") + " " + (company.name if company else "")).lower()
    # When no contact title, also search company intel for keyword signals
    if (not contact or not contact.title) and company and company.intel_summary:
        search += " " + company.intel_summary[:500].lower()
    for keywords, label in EXPERTISE_MAP:
        if any(k in search for k in keywords):
            return label
    return _EXPERTISE_DEFAULT


_ROLE_LABELS = [
    (["ceo", "chief executive"], "CEO"),
    (["cto", "chief technology"], "CTO"),
    (["cfo", "chief financial"], "CFO"),
    (["coo", "chief operating"], "COO"),
    (["cpo", "chief product"], "CPO"),
    (["cro", "chief revenue"], "CRO"),
    (["cmo", "chief marketing"], "CMO"),
    (["chro", "chief people"], "CHRO"),
    (["managing director"], "Managing Director"),
    (["general partner"], "General Partner"),
    (["principal"], "Principal"),
    (["partner"], "Partner"),
    (["svp", "senior vice president"], "SVP"),
    (["evp", "executive vice president"], "EVP"),
    (["vp ", "vice president"], "VP"),
    (["director"], "Director"),
    (["head of"], "Head"),
    (["manager"], "Manager"),
    (["founder", "co-founder"], "Founder"),
]

_SENIOR_ROLES = {"CEO", "CTO", "CFO", "COO", "CPO", "CRO", "CMO", "CHRO", "Founder",
                 "Managing Director", "General Partner", "Partner", "Principal",
                 "SVP", "EVP", "VP", "Director", "Head"}


def _short_role_label(contact) -> str:
    if not contact or not contact.title:
        return "your role"
    title = contact.title.lower()
    for keywords, label in _ROLE_LABELS:
        if any(k in title for k in keywords):
            return label
    return contact.title.split(",")[0].strip()


def _build_escalation_subject(contact, company, first, is_mit) -> str:
    if is_mit:
        return "Fellow Sloan alum — quick question"
    co_name = company.name if company else "your company"
    if first == "there":
        return f"Reaching out directly — {co_name}"
    role_label = _short_role_label(contact)
    if role_label in _SENIOR_ROLES:
        return f"{first} — quick question"
    return f"{first} — reaching out directly"


@router.post("/{record_id}/draft-template")
async def draft_template(
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

    # Fetch prior canonical message early so escalation branch can reference it
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

    intel = ""
    if followup_type == "escalation":
        from app.services.draft_helpers import (
            _derive_expertise_from_title, _AMBIGUOUS_NAMES,
            _pick_headline, _humanize_headline, _extract_curated_opener,
            _extract_headlines_from_intel_dump,
        )
        from app.services.outreach_generator import generate_escalation_draft
        is_mit = getattr(contact, "is_mit_alum", None) if contact else None

        # Auto-fetch intel if missing (free: RSS + DB reads, no Anthropic API)
        intel = (company.intel_summary or "").strip() if company else ""
        if not intel and company:
            try:
                from app.services.company_intel import generate_company_brief
                intel = await generate_company_brief(company, session)
                company.intel_summary = intel
                company.updated_at = datetime.utcnow().isoformat()
                session.add(company)
                session.commit()
            except Exception:
                intel = ""

        # Try AI-powered personalized draft first
        ai_draft = await generate_escalation_draft(contact, company, prior_message, "linkedin_escalation")
        if ai_draft:
            subject = ai_draft["subject"]
            body = ai_draft["body"]
        else:
            # Fallback: template-based draft
            # Fetch disambiguated news headlines
            news_headlines: list = []
            if company:
                try:
                    from app.services.company_intel import fetch_news
                    suffix = " fintech payments" if company_name.lower() in _AMBIGUOUS_NAMES else ""
                    news_headlines = await fetch_news(company_name + suffix, max_items=8)
                except Exception:
                    pass

            # Opener: fresh news > cached intel news > curated intel prose > MIT alum > expertise-based
            # Note: live fetch_news may fail silently on cloud IPs (Google News blocks); use intel dump as fallback
            headline = _pick_headline(news_headlines, company_name)
            if not headline and intel:
                dump_headlines = _extract_headlines_from_intel_dump(intel)
                headline = _pick_headline(dump_headlines, company_name)
            curated = _extract_curated_opener(intel)

            expertise_q = _derive_expertise_from_title(contact.title or "", company_name) if contact and contact.title else f"what you are building at {company_name}"

            if headline:
                opener = _humanize_headline(headline, company_name)
            elif curated:
                if curated.lower().startswith(company_name.lower()):
                    opener = curated if curated.endswith(".") else curated + "."
                else:
                    curated_lc = curated[0].lower() + curated[1:]
                    opener = f"I have been following {company_name}, {curated_lc.rstrip('.')}."
            elif is_mit:
                opener = "I am a fellow MIT Sloan alum."
            else:
                expertise_short = expertise_q.replace(f" at {company_name}", "").strip()
                opener = f"I have been following {company_name}'s work on {expertise_short} and wanted to reach out directly."

            linkedin_bridge_clause = (
                f"since we connected on LinkedIn, {company_name}'s work on {expertise_q.replace(f' at {company_name}', '').strip()} has stayed on my mind"
                if prior_message else ""
            )

            if prior_message and linkedin_bridge_clause:
                question = f"I dropped you a note on LinkedIn last week — {linkedin_bridge_clause} — and wanted to ask directly: would you have 15 minutes to share how you are thinking about {expertise_q}?"
            else:
                question = f"Would you have 15 minutes to share how you are thinking about {expertise_q} from your seat at {company_name}?"

            if contact and contact.title:
                title_words = ' '.join(contact.title.split()[:3])
                subject = f"A question for the {title_words} at {company_name}"
            else:
                subject = f"A question about {company_name}"

            opener_block = f"{opener}\n\n" if opener else ""
            body = (
                f"Hi {first},\n\n"
                f"{opener_block}"
                f"{question}"
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
    elif followup_type == "linkedin_dm":
        expertise = _derive_expertise(contact, company)
        is_mit = getattr(contact, "is_mit_alum", None) if contact else None
        opener = "I am a fellow MIT Sloan alum." if is_mit else f"I noticed we share an interest in {expertise}."
        subject = None
        body = (
            f"Hi {first},\n\n"
            f"{opener} I'd love to hear your perspective on what you're building at {company_name} "
            f"and share some of what I'm seeing on the operator side. "
            f"Open to a quick 20-minute chat?"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid followup_type")

    guessed_email = None
    if contact and contact.email:
        guessed_email = contact.email
    elif contact and company:
        ns = _contact_next_step(contact, company)
        guessed_email = ns.get("guessed_email")

    return {"subject": subject, "body": body, "guessed_email": guessed_email, "prior_message": prior_message, "intel": intel if followup_type == "escalation" else ""}


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

    today = datetime.now(_EASTERN)

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
        if req.subject and (not email_record.subject or "logged via MCP" in (email_record.subject or "").lower()):
            email_record.subject = req.subject
            session.add(email_record)

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

    # Fall back to sender email from conversation history if contact has no email on record
    if not to_email:
        reply_msg = session.exec(
            select(ConversationMessage)
            .where(ConversationMessage.outreach_record_id == record.id)
            .where(ConversationMessage.message_type == "reply")
            .order_by(ConversationMessage.message_date.desc())  # type: ignore[arg-type]
        ).first()
        if reply_msg and reply_msg.from_email:
            to_email = reply_msg.from_email

    subject_enc = urllib.parse.quote(req.subject or "", safe="")
    body_enc = urllib.parse.quote(req.body or "", safe="")
    to_enc = urllib.parse.quote(to_email, safe="@.")
    gmail_url = f"https://mail.google.com/mail/?view=cm&to={to_enc}&su={subject_enc}&body={body_enc}"

    return {"mailto_url": gmail_url, "to_email": to_email or None}


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
    if req.followup_day == 0:
        record.post_meeting_followup_sent = True
        record.follow_up_3_sent = True
        record.post_meeting_2_due = add_business_days(today, 3).isoformat()
    elif req.followup_day == -1:
        record.post_meeting_2_sent = True
    elif req.followup_day == 3:
        record.follow_up_3_sent = True
        record.follow_up_7_due = add_business_days(today, 4).isoformat()
    else:
        record.follow_up_7_sent = True
        record.response_status = "ghosted"
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
    to_enc = urllib.parse.quote(to_email, safe="@.")
    mailto_url = f"https://mail.google.com/mail/?view=cm&to={to_enc}&su={subject_enc}&body={body_enc}"

    today = date.today()
    if req.followup_day == 3:
        record.follow_up_3_sent = True
        record.follow_up_7_due = add_business_days(today, 4).isoformat()
    else:
        record.follow_up_7_sent = True
        record.response_status = "ghosted"
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
