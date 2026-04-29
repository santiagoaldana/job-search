"""Contacts router — LinkedIn CSV import, quick-add, update."""

import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Contact, Company

router = APIRouter()


class QuickAddRequest(BaseModel):
    name: str
    title: Optional[str] = None
    company_name: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    met_via: Optional[str] = None
    relationship_notes: Optional[str] = None
    introduced_by_contact_id: Optional[int] = None


class ContactUpdateRequest(BaseModel):
    met_via: Optional[str] = None
    relationship_notes: Optional[str] = None
    met_at_event_id: Optional[int] = None
    warmth: Optional[str] = None
    outreach_status: Optional[str] = None
    title: Optional[str] = None
    introduced_by_contact_id: Optional[int] = None


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


@router.post("/quick-add")
def quick_add_contact(req: QuickAddRequest, session: Session = Depends(get_session)):
    all_companies = session.exec(select(Company).where(Company.is_archived == False)).all()
    company_index = {(c.name or "").lower(): c.id for c in all_companies if c.name}
    company_id = _match_company_from_index(req.company_name or "", company_index)

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

    session.add(contact)
    if company_id:
        _refresh_advocacy_scores([company_id], session)
    session.commit()
    session.refresh(contact)

    matched_company = None
    if company_id:
        c = session.get(Company, company_id)
        matched_company = c.name if c else None

    return {"ok": True, "contact_id": contact.id, "matched_company": matched_company}


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
