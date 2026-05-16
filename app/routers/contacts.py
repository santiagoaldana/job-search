"""Contacts router — LinkedIn CSV import, quick-add, update."""

import base64
import csv
import io
import json
from datetime import datetime, date, timedelta
from typing import Optional
import anthropic
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Contact, Company, OutreachRecord, Reference
from app.services.email_finder import determine_next_step

router = APIRouter()


@router.get("")
def list_contacts(session: Session = Depends(get_session)):
    """Return all contacts with their company name, ordered by name."""
    contacts = session.exec(select(Contact).order_by(Contact.name)).all()
    result = []
    for c in contacts:
        company = session.get(Company, c.company_id) if c.company_id else None
        result.append({
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "company_name": company.name if company else None,
        })
    return result


class QuickAddRequest(BaseModel):
    name: str
    title: Optional[str] = None
    company_name: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    met_via: Optional[str] = None
    relationship_notes: Optional[str] = None
    introduced_by_contact_id: Optional[int] = None
    outreach_status: Optional[str] = None  # none|connection_requested|linkedin_dm|emailed|drafted
    is_mit_alum: Optional[bool] = None


class ContactUpdateRequest(BaseModel):
    met_via: Optional[str] = None
    relationship_notes: Optional[str] = None
    met_at_event_id: Optional[int] = None
    warmth: Optional[str] = None
    outreach_status: Optional[str] = None
    title: Optional[str] = None
    introduced_by_contact_id: Optional[int] = None
    email: Optional[str] = None
    email_guessed: Optional[bool] = None
    email_invalid: Optional[bool] = None
    email_patterns_tried: Optional[str] = None
    connection_request_variant: Optional[str] = None
    is_mit_alum: Optional[bool] = None
    connection_degree: Optional[int] = None
    referral_target_company_id: Optional[int] = None
    connected_on: Optional[str] = None
    snooze_until: Optional[str] = None


def _match_company_from_index(company_name: str, company_index: dict) -> Optional[int]:
    """Match company name against pre-loaded index. O(n) but done in Python, not DB."""
    if not company_name:
        return None
    name_lower = company_name.lower().strip()
    # Exact match first
    if name_lower in company_index:
        return company_index[name_lower]
    # Substring match
    for cname, cid in company_index.items():
        if cname in name_lower or name_lower in cname:
            return cid
    return None


def _refresh_advocacy_scores(company_ids: list, session: Session):
    # Count contacts per company in one pass
    from collections import Counter
    all_contacts = session.exec(
        select(Contact).where(Contact.connection_degree == 1, Contact.company_id != None)
    ).all()
    counts = Counter(c.company_id for c in all_contacts)

    for cid in set(company_ids):
        company = session.get(Company, cid)
        if not company:
            continue
        new_score = min(10.0, counts.get(cid, 0) * 1.5 + 1.0)
        if new_score > company.advocacy_score:
            company.advocacy_score = new_score
            company.lamp_score = round(
                (company.motivation * 0.5)
                + (company.postings_score * 0.3)
                + (company.advocacy_score * 0.2),
                2,
            )
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)


@router.post("/import-linkedin")
async def import_linkedin_csv(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Parse LinkedIn Connections CSV and cross-reference against funnel companies.
    Optimised for large files: loads all companies + contacts into memory first."""
    content = (await file.read()).decode("utf-8", errors="ignore")
    lines = content.splitlines()

    # LinkedIn CSV starts with notes before the actual header row
    csv_start = None
    for i, line in enumerate(lines):
        if line.startswith("First Name"):
            csv_start = i
            break

    if csv_start is None:
        raise HTTPException(status_code=400, detail="Could not find CSV header. Expected 'First Name' column.")

    # --- Load everything into memory upfront (fast, no per-row DB queries) ---
    all_companies = session.exec(
        select(Company).where(Company.is_archived == False)
    ).all()
    company_index = {(c.name or "").lower(): c.id for c in all_companies if c.name}

    all_contacts = session.exec(select(Contact)).all()
    url_index = {c.linkedin_url: c for c in all_contacts if c.linkedin_url}
    name_index = {c.name.lower(): c for c in all_contacts if c.name}

    reader = csv.DictReader(lines[csv_start:])
    imported = 0
    matched_company_ids = []
    new_contacts = []

    for row in reader:
        first = (row.get("First Name") or "").strip()
        last = (row.get("Last Name") or "").strip()
        name = f"{first} {last}".strip()
        if not name:
            continue

        company_name = (row.get("Company") or "").strip()
        position = (row.get("Position") or "").strip()
        linkedin_url = (row.get("URL") or "").strip()
        email = (row.get("Email Address") or "").strip() or None
        connected_on = (row.get("Connected On") or "").strip() or None

        company_id = _match_company_from_index(company_name, company_index)

        # Upsert using in-memory indexes
        existing = url_index.get(linkedin_url) if linkedin_url else None
        if not existing:
            existing = name_index.get(name.lower())

        if existing:
            changed = False
            if company_id and not existing.company_id:
                existing.company_id = company_id
                matched_company_ids.append(company_id)
                changed = True
            if position and not existing.title:
                existing.title = position
                changed = True
            if email and not existing.email:
                existing.email = email
                changed = True
            if changed:
                session.add(existing)
        else:
            contact = Contact(
                name=name,
                title=position or None,
                linkedin_url=linkedin_url or None,
                email=email,
                company_id=company_id,
                connection_degree=1,
                warmth="warm" if company_id else "cold",
                connected_on=connected_on,
            )
            new_contacts.append(contact)
            # Update in-memory index so duplicates within the CSV are caught
            if linkedin_url:
                url_index[linkedin_url] = contact
            name_index[name.lower()] = contact
            if company_id:
                matched_company_ids.append(company_id)

        imported += 1

    for c in new_contacts:
        session.add(c)

    _refresh_advocacy_scores(matched_company_ids, session)
    session.commit()

    matched_company_names = []
    for cid in set(matched_company_ids):
        company = session.get(Company, cid)
        if company:
            matched_company_names.append(company.name)

    return {
        "imported": imported,
        "matched_to_funnel": len(set(matched_company_ids)),
        "new_warm_paths": matched_company_names[:10],
    }


def _find_duplicate_contact(session, company_id, name: str, title: Optional[str], email: Optional[str], linkedin_url: Optional[str]) -> Optional[Contact]:
    """Return an existing Contact that is likely the same person, or None."""
    if not company_id:
        return None
    existing = session.exec(select(Contact).where(Contact.company_id == company_id)).all()
    for c in existing:
        if email and c.email and c.email.lower().strip() == email.lower().strip():
            return c
        if linkedin_url and c.linkedin_url and c.linkedin_url.strip() == linkedin_url.strip():
            return c
        if name and title and c.name and c.title:
            if c.name.lower().strip() == name.lower().strip() and c.title.lower().strip() == title.lower().strip():
                return c
    return None


@router.post("/quick-add")
def quick_add_contact(req: QuickAddRequest, session: Session = Depends(get_session)):
    all_companies = session.exec(select(Company).where(Company.is_archived == False)).all()
    company_index = {(c.name or "").lower(): c.id for c in all_companies if c.name}
    company_id = _match_company_from_index(req.company_name or "", company_index)

    # Auto-create company if a name was provided but didn't match anything
    if req.company_name and not company_id:
        new_company = Company(
            name=req.company_name.strip(),
            stage="pool",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )
        session.add(new_company)
        session.flush()
        company_id = new_company.id

    # Check for existing contact that matches on email, LinkedIn URL, or name+title
    existing = _find_duplicate_contact(session, company_id, req.name, req.title, req.email, req.linkedin_url)
    if existing:
        # Fill in any missing fields from the new request
        changed = False
        if req.email and not existing.email:
            existing.email = req.email; changed = True
        if req.linkedin_url and not existing.linkedin_url:
            existing.linkedin_url = req.linkedin_url; changed = True
        if req.title and not existing.title:
            existing.title = req.title; changed = True
        if req.met_via and not existing.met_via:
            existing.met_via = req.met_via; changed = True
        if req.relationship_notes and not existing.relationship_notes:
            existing.relationship_notes = req.relationship_notes; changed = True
        if req.outreach_status and existing.outreach_status == "none":
            existing.outreach_status = req.outreach_status; changed = True
        if req.is_mit_alum is not None and existing.is_mit_alum is None:
            existing.is_mit_alum = req.is_mit_alum; changed = True
        if changed:
            session.add(existing)
            session.commit()
            session.refresh(existing)
        contact = existing
    else:
        contact = Contact(
            name=req.name,
            title=req.title,
            linkedin_url=req.linkedin_url,
            email=req.email,
            company_id=company_id,
            connection_degree=1,
            warmth="warm" if company_id else "cold",
        )
        contact.met_via = req.met_via
        contact.relationship_notes = req.relationship_notes
        contact.introduced_by_contact_id = req.introduced_by_contact_id
        if req.outreach_status:
            contact.outreach_status = req.outreach_status
        if req.is_mit_alum is not None:
            contact.is_mit_alum = req.is_mit_alum

        session.add(contact)
        if company_id:
            _refresh_advocacy_scores([company_id], session)
        session.commit()
        session.refresh(contact)

    matched_company_obj = session.get(Company, company_id) if company_id else None
    matched_company = matched_company_obj.name if matched_company_obj else None

    next_step = determine_next_step(contact, matched_company_obj)

    return {
        "ok": True,
        "contact_id": contact.id,
        "matched_company": matched_company,
        "next_step": next_step,
    }


@router.post("/parse-screenshot")
async def parse_contact_screenshot(file: UploadFile = File(...)):
    """Extract contact fields from a LinkedIn profile screenshot using Claude vision."""
    image_bytes = await file.read()
    image_b64 = base64.b64encode(image_bytes).decode()
    media_type = file.content_type or "image/png"

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract contact info from this LinkedIn profile screenshot. "
                        "Return JSON only — no markdown, no explanation — with these fields: "
                        "name, title, company_name, linkedin_url (from the URL bar or profile link if visible), location, is_mit_alum. "
                        "is_mit_alum: true if Education section shows MIT, MIT Sloan, or Massachusetts Institute of Technology. "
                        "false if education is visible but no MIT. null if education not visible. "
                        "Use null for any missing fields."
                    ),
                },
            ],
        }],
    )
    try:
        return json.loads(response.content[0].text.strip())
    except Exception:
        return {"name": None, "title": None, "company_name": None, "linkedin_url": None, "location": None, "is_mit_alum": None}


class LogInteractionRequest(BaseModel):
    contact_name: str
    company_name: Optional[str] = None
    note: str
    had_reply: bool = True
    channel: str = "linkedin"


@router.post("/log-interaction")
def log_interaction(req: LogInteractionRequest, session: Session = Depends(get_session)):
    """Log a LinkedIn or email interaction with an existing contact."""
    name_lower = req.contact_name.lower()
    candidates = session.exec(select(Contact)).all()
    contact = next((c for c in candidates if name_lower in (c.name or "").lower()), None)

    if contact is None:
        raise HTTPException(status_code=404, detail=f"Contact '{req.contact_name}' not found")

    if req.company_name and contact.company_id:
        company_name_lower = req.company_name.lower()
        for c in candidates:
            if name_lower in (c.name or "").lower() and c.company_id:
                company = session.get(Company, c.company_id)
                if company and company_name_lower in (company.name or "").lower():
                    contact = c
                    break

    existing = contact.relationship_notes or ""
    separator = "\n" if existing else ""
    contact.relationship_notes = existing + separator + req.note

    if contact.outreach_status in ("none", "drafted"):
        contact.outreach_status = req.channel if req.channel in ("linkedin_dm", "emailed") else "linkedin_dm"

    session.add(contact)

    today = datetime.utcnow().date()

    def _add_business_days(start: date, days: int) -> date:
        d = start
        added = 0
        while added < days:
            d += timedelta(days=1)
            if d.weekday() < 5:
                added += 1
        return d

    follow_up_3 = _add_business_days(today, 3).isoformat()
    follow_up_7 = _add_business_days(today, 7).isoformat()

    session.commit()

    try:
        prior_message = req.note
        prior = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == contact.id)
            .where(OutreachRecord.outreach_message.is_not(None))  # type: ignore[union-attr]
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if prior and prior.outreach_message:
            prior_message = prior.outreach_message

        record = OutreachRecord(
            company_id=contact.company_id,
            contact_id=contact.id,
            channel=req.channel,
            sent_at=datetime.utcnow().isoformat(),
            body=req.note,
            outreach_message=prior_message,
            response_status="positive" if req.had_reply else "pending",
            follow_up_3_due=follow_up_3,
            follow_up_7_due=follow_up_7,
        )
        session.add(record)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save outreach record: {str(e)}")

    company = session.get(Company, contact.company_id) if contact.company_id else None
    return {
        "ok": True,
        "contact_id": contact.id,
        "contact_name": contact.name,
        "company_name": company.name if company else None,
    }


@router.get("/{contact_id}")
def get_contact(contact_id: int, session: Session = Depends(get_session)):
    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.patch("/{contact_id}")
def update_contact(
    contact_id: int,
    req: ContactUpdateRequest,
    session: Session = Depends(get_session),
):
    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, val in req.dict(exclude_none=True).items():
        if hasattr(contact, field):
            setattr(contact, field, val)

    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


class MergeContactRequest(BaseModel):
    keep_id: int
    discard_id: int


@router.post("/merge")
def merge_contacts(req: MergeContactRequest, session: Session = Depends(get_session)):
    keep = session.get(Contact, req.keep_id)
    discard = session.get(Contact, req.discard_id)
    if not keep or not discard:
        raise HTTPException(status_code=404, detail="Contact not found")
    if keep.id == discard.id:
        raise HTTPException(status_code=400, detail="Cannot merge a contact with itself")

    # Concatenate text fields if both have content; fill if only discard has content
    for field in ("relationship_notes", "met_via"):
        keep_val = getattr(keep, field, None)
        discard_val = getattr(discard, field, None)
        if keep_val and discard_val and keep_val.strip() != discard_val.strip():
            setattr(keep, field, f"{keep_val} | {discard_val}")
        elif not keep_val and discard_val:
            setattr(keep, field, discard_val)

    # Fill missing scalar fields from discard
    for field in ("email", "linkedin_url", "title", "connected_on", "is_mit_alum"):
        if not getattr(keep, field, None) and getattr(discard, field, None):
            setattr(keep, field, getattr(discard, field))

    # Reassign child rows
    for rec in session.exec(select(OutreachRecord).where(OutreachRecord.contact_id == discard.id)).all():
        rec.contact_id = keep.id
        session.add(rec)
    for ref in session.exec(select(Reference).where(Reference.contact_id == discard.id)).all():
        ref.contact_id = keep.id
        session.add(ref)

    session.add(keep)
    session.delete(discard)
    session.commit()
    session.refresh(keep)
    return keep


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, session: Session = Depends(get_session)):
    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    session.delete(contact)
    session.commit()
    return {"ok": True}


@router.post("/{contact_id}/draft-dm")
def draft_linkedin_dm(contact_id: int, session: Session = Depends(get_session)):
    """Generate a Dalton-method thank-you DM for a LinkedIn acceptance using Claude."""
    from app.services.outreach_generator import build_outreach_context

    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    company = session.get(Company, contact.company_id) if contact.company_id else None

    ctx = build_outreach_context(
        company=company or type("_C", (), {"name": "their company", "intel_summary": None, "stage": None})(),
        contact=contact,
        email_type="linkedin_dm",
        context="Just accepted LinkedIn connection request",
    )

    prompt = f"""You are drafting a LinkedIn DM for Santiago Aldana using the Dalton method.

CONTEXT:
{json.dumps(ctx, indent=2)}

DALTON RULES (non-negotiable):
- 75 words maximum
- The message must be primarily about THEM: their work, their company, their challenge
- Open by naming something specific about what they are building or the hard problem they are solving
- Santiago's credential appears once, briefly, as a bridge ("I ran X, so I know this problem firsthand") — never as the opener
- End with an open question about their perspective or strategy — not a call to action
- No em dashes, en dashes, or hyphens anywhere
- Forbidden: "hope this finds you", "I am reaching out", "excited to", "would love to", "opportunity", "really glad we connected"
- Return ONLY the message body — no subject line, no JSON, no signature

Contact: {contact.name}, {contact.title or "unknown title"} at {company.name if company else "their company"}"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    message = response.content[0].text.strip()
    return {"message": message}


@router.post("/{contact_id}/bounce")
def mark_email_bounce(contact_id: int, session: Session = Depends(get_session)):
    """Mark contact email as bounced, advance to next pattern, return updated next_step."""
    import json as _json
    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Record the current email as tried
    tried = _json.loads(contact.email_patterns_tried or "[]")
    if contact.email and contact.email not in tried:
        tried.append(contact.email)
    contact.email_patterns_tried = _json.dumps(tried)
    contact.email_invalid = True
    contact.email = None
    contact.email_guessed = False

    session.add(contact)
    session.commit()
    session.refresh(contact)

    company = session.get(Company, contact.company_id) if contact.company_id else None
    next_step = determine_next_step(contact, company)
    return {"ok": True, "next_step": next_step}


@router.get("/{contact_id}/next-step")
def get_contact_next_step(contact_id: int, session: Session = Depends(get_session)):
    """Return the recommended next outreach action for a contact."""
    contact = session.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    company = session.get(Company, contact.company_id) if contact.company_id else None
    next_step = determine_next_step(contact, company)
    return {
        "contact_id": contact_id,
        "contact_name": contact.name,
        "company_name": company.name if company else None,
        "next_step": next_step,
    }
