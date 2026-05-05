"""Companies router — LAMP list CRUD, stage transitions, intel refresh."""

import asyncio
from datetime import datetime
from typing import List, Optional, Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Company, Contact, Lead, OutreachRecord, Application

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CompanyUpdate(BaseModel):
    motivation: Optional[int] = None
    stage: Optional[str] = None
    is_archived: Optional[bool] = None
    funding_stage: Optional[str] = None
    career_page_url: Optional[str] = None
    greenhouse_slug: Optional[str] = None
    lever_slug: Optional[str] = None
    ashby_slug: Optional[str] = None
    wttj_slug: Optional[str] = None
    org_notes: Optional[str] = None
    crunchbase_url: Optional[str] = None
    intel_summary: Optional[str] = None


class CompanyCreate(BaseModel):
    name: str
    motivation: int = 7
    funding_stage: Literal["series_b", "series_c", "series_d", "series_e", "series_f", "series_g", "series_h", "public", "unknown"] = "unknown"
    career_page_url: Optional[str] = None
    suggested_by_ai: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_companies(
    active_only: bool = Query(True, description="Only motivation ≥ 7, not archived"),
    stage: Optional[str] = Query(None),
    motivation_min: int = Query(1),
    q: Optional[str] = Query(None, description="Search by company name"),
    session: Session = Depends(get_session),
):
    stmt = select(Company)
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    elif active_only:
        stmt = stmt.where(Company.is_archived == False, Company.motivation >= 7)
    if stage:
        stmt = stmt.where(Company.stage == stage)
    if motivation_min > 1:
        stmt = stmt.where(Company.motivation >= motivation_min)
    companies = session.exec(stmt.order_by(Company.lamp_score.desc())).all()
    return companies


STAGE_GROUPS = {
    "target":  {"pool", "researched"},
    "in_play": {"outreach", "response", "meeting", "applied", "interview"},
    "closed":  {"offer", "closed"},
}

DISPLAY_TO_INTERNAL = {
    "target": "researched",
    "in_play": "outreach",
    "closed": "closed",
}


@router.get("/funnel")
def funnel_view(session: Session = Depends(get_session)):
    """Return active companies grouped into 3 stages: target / in_play / closed."""
    companies = session.exec(
        select(Company)
        .where(Company.is_archived == False, Company.motivation >= 7)
        .order_by(Company.lamp_score.desc())
    ).all()

    result = {"target": [], "in_play": [], "closed": []}
    for c in companies:
        bucket = "target"
        for group, stages in STAGE_GROUPS.items():
            if c.stage in stages:
                bucket = group
                break
        result[bucket].append({
            "id": c.id,
            "name": c.name,
            "lamp_score": c.lamp_score,
            "motivation": c.motivation,
            "funding_stage": c.funding_stage,
            "headcount_range": c.headcount_range,
            "stage": c.stage,
            "intel_summary": c.intel_summary,
            "org_notes": c.org_notes,
        })
    return result


@router.get("/{company_id}")
def get_company(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    contacts_raw = session.exec(
        select(Contact).where(Contact.company_id == company_id)
    ).all()
    leads = session.exec(
        select(Lead).where(Lead.company_id == company_id, Lead.status.in_(["active", "applied"]))
        .order_by(Lead.fit_score.desc())
    ).all()
    outreach = session.exec(
        select(OutreachRecord).where(OutreachRecord.company_id == company_id)
        .order_by(OutreachRecord.sent_at.desc())
    ).all()
    applications = session.exec(
        select(Application).where(Application.company_id == company_id)
    ).all()

    # Enrich contacts with introducer name
    contacts = []
    for c in contacts_raw:
        d = c.dict()
        if c.introduced_by_contact_id:
            introducer = session.get(Contact, c.introduced_by_contact_id)
            d["introduced_by_name"] = introducer.name if introducer else None
        else:
            d["introduced_by_name"] = None
        contacts.append(d)

    # Referral contacts — people who don't work here but can open doors
    referral_contacts_raw = session.exec(
        select(Contact).where(Contact.referral_target_company_id == company_id)
    ).all()
    referral_contacts = []
    for c in referral_contacts_raw:
        current_company = session.get(Company, c.company_id) if c.company_id else None
        referral_contacts.append({
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "current_company_name": current_company.name if current_company else None,
            "warmth": c.warmth,
            "linkedin_url": c.linkedin_url,
            "relationship_notes": c.relationship_notes,
        })

    return {
        "company": company,
        "contacts": contacts,
        "leads": leads,
        "outreach": outreach,
        "applications": applications,
        "referral_contacts": referral_contacts,
    }


@router.patch("/{company_id}")
def update_company(
    company_id: int,
    update: CompanyUpdate,
    session: Session = Depends(get_session),
):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    data = update.dict(exclude_unset=True)
    for k, v in data.items():
        setattr(company, k, v)

    # Recompute lamp_score when motivation changes
    if "motivation" in data:
        company.lamp_score = round(
            (company.motivation * 0.5)
            + (company.postings_score * 0.3)
            + (company.advocacy_score * 0.2),
            2,
        )

    company.updated_at = datetime.utcnow().isoformat()
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


class StageRequest(BaseModel):
    stage: str


@router.post("/{company_id}/stage")
def set_stage(
    company_id: int,
    req: StageRequest,
    session: Session = Depends(get_session),
):
    # Accept display names (target/in_play/closed) and map to internal stages
    stage = DISPLAY_TO_INTERNAL.get(req.stage, req.stage)
    valid = {"pool", "researched", "outreach", "response", "meeting",
             "applied", "interview", "offer", "closed"}
    if stage not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.stage = stage
    company.updated_at = datetime.utcnow().isoformat()
    session.add(company)
    session.commit()
    return {"id": company_id, "stage": stage}


@router.post("/{company_id}/archive")
def archive_company(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_archived = True
    company.updated_at = datetime.utcnow().isoformat()
    session.add(company)
    session.commit()
    return {"id": company_id, "archived": True}


class BulkArchiveRequest(BaseModel):
    names: List[str]


@router.post("/bulk-archive")
def bulk_archive(req: BulkArchiveRequest, session: Session = Depends(get_session)):
    """Archive a list of companies by exact name match."""
    archived = 0
    for name in req.names:
        company = session.exec(select(Company).where(Company.name == name)).first()
        if company:
            company.is_archived = True
            company.motivation = 1
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)
            archived += 1
    session.commit()
    return {"archived": archived, "requested": len(req.names)}


@router.post("/enrich-all")
async def enrich_all(background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    """Batch-enrich all unenriched companies via Apollo. Runs in background."""
    companies = session.exec(
        select(Company).where(Company.apollo_enriched_at == None, Company.is_archived == False)
    ).all()

    async def _run():
        for c in companies:
            try:
                from app.services.apollo_enricher import enrich_company as _enrich
                data = await _enrich(c.name)
                if data.get("funding_stage"):
                    c.funding_stage = data["funding_stage"]
                if data.get("headcount_range"):
                    c.headcount_range = data["headcount_range"]
                if data.get("description"):
                    c.org_notes = data["description"]
                c.apollo_enriched_at = datetime.utcnow().isoformat()
                session.add(c)
                session.commit()
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[enrich] {c.name}: {e}")

    background_tasks.add_task(_run)
    return {"started": True, "companies": len(companies)}


@router.post("")
def create_company(data: CompanyCreate, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    company = Company(
        name=data.name,
        motivation=data.motivation,
        funding_stage=data.funding_stage,
        career_page_url=data.career_page_url,
        suggested_by_ai=data.suggested_by_ai,
        is_archived=False,
        stage="pool",
        lamp_score=round(data.motivation * 0.5 + 1.0 * 0.3 + 1.0 * 0.2, 2),
    )
    session.add(company)
    session.commit()
    session.refresh(company)

    async def _enrich_new(company_id: int):
        from app.services.apollo_enricher import enrich_company as _enrich
        from app.database import engine as _engine
        with Session(_engine) as s:
            c = s.get(Company, company_id)
            if not c:
                return
            try:
                d = await _enrich(c.name)
                if d.get("funding_stage"):
                    c.funding_stage = d["funding_stage"]
                if d.get("headcount_range"):
                    c.headcount_range = d["headcount_range"]
                if d.get("description"):
                    c.org_notes = d["description"]
                c.apollo_enriched_at = datetime.utcnow().isoformat()
                s.add(c)
                s.commit()
            except Exception as e:
                print(f"[enrich] {c.name}: {e}")

    background_tasks.add_task(_enrich_new, company.id)
    return company


@router.post("/{company_id}/find-contacts")
async def find_contacts(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        from app.services.contact_finder import find_contacts as _find_contacts

        # Infer domain from career page URL or guess from name
        domain = None
        if company.career_page_url:
            m = __import__("re").search(r"https?://(?:www\.)?([^/]+)", company.career_page_url)
            if m:
                domain = m.group(1)

        contacts_data = await _find_contacts(company.name, company_id, domain)

        # Persist new contacts, skip duplicates by name
        existing_names = {c.name.lower() for c in session.exec(
            select(Contact).where(Contact.company_id == company_id)
        ).all()}

        new_contacts = []
        for cd in contacts_data:
            if cd["name"].lower() in existing_names:
                continue
            contact = Contact(
                company_id=company_id,
                name=cd["name"],
                title=cd.get("title") or "",
                email=cd.get("email") or "",
                linkedin_url=cd.get("linkedin_url") or "",
                connection_degree=3,
                warmth="cold",
            )
            session.add(contact)
            new_contacts.append(cd)
            existing_names.add(cd["name"].lower())

        session.commit()

        return {"found": len(new_contacts), "contacts": new_contacts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/network-path")
async def get_network_path(company_id: int, refresh: bool = False, session: Session = Depends(get_session)):
    """Return direct connections + Claude-inferred likely intro connectors. Caches result in DB."""
    import json as _json
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    direct = session.exec(
        select(Contact).where(
            Contact.company_id == company_id,
            Contact.connection_degree == 1,
        )
    ).all()

    direct_payload = [
        {
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "linkedin_url": c.linkedin_url,
            "warmth": c.warmth,
            "outreach_status": c.outreach_status,
            "met_via": getattr(c, 'met_via', None),
            "relationship_notes": getattr(c, 'relationship_notes', None),
        }
        for c in direct
    ]

    # Return cached likely_connectors unless refresh requested
    if not refresh and company.network_path_json:
        cached = _json.loads(company.network_path_json)
        return {
            "direct_connections": direct_payload,
            "likely_connectors": cached.get("likely_connectors", []),
            "has_warm_path": len(direct) > 0,
        }

    all_1st = session.exec(
        select(Contact).where(
            Contact.connection_degree == 1,
            Contact.company_id != None,
            Contact.company_id != company_id,
        )
    ).all()

    likely_connectors = []
    if all_1st:
        contacts_text = "\n".join(
            f"- {c.name} ({c.title or 'title unknown'}) at company_id {c.company_id}"
            for c in all_1st[:40]
        )
        prompt = f"""Santiago Aldana is targeting {company.name} ({company.intel_summary or 'fintech company'}).

These are his 1st-degree LinkedIn contacts at other companies:
{contacts_text}

Which 3-5 of these contacts are most likely to know someone at {company.name}?
Consider: shared fintech/payments industry, geographic proximity to Boston, alumni connections.

Return ONLY a JSON array:
[{{"name": "...", "title": "...", "reason": "one sentence why they likely know someone at {company.name}"}}]"""

        try:
            import anthropic
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            likely_connectors = _json.loads(raw)
        except Exception:
            likely_connectors = []

    # Cache result
    company.network_path_json = _json.dumps({"likely_connectors": likely_connectors})
    session.add(company)
    session.commit()

    return {
        "direct_connections": direct_payload,
        "likely_connectors": likely_connectors,
        "has_warm_path": len(direct) > 0,
    }


@router.post("/{company_id}/enrich")
async def enrich_single(company_id: int, session: Session = Depends(get_session)):
    """Enrich a single company via Apollo (funding, headcount, description)."""
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    from app.services.apollo_enricher import enrich_company as _enrich
    data = await _enrich(company.name)
    if data.get("funding_stage"):
        company.funding_stage = data["funding_stage"]
    if data.get("headcount_range"):
        company.headcount_range = data["headcount_range"]
    if data.get("description"):
        company.org_notes = data["description"]
    company.apollo_enriched_at = datetime.utcnow().isoformat()
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.post("/{company_id}/intel/refresh")
async def refresh_intel(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        from app.services.company_intel import generate_company_brief
        brief = await generate_company_brief(company.name)
        company.intel_summary = brief
        company.last_intel_refresh = datetime.utcnow().isoformat()
        company.updated_at = datetime.utcnow().isoformat()
        session.add(company)
        session.commit()
        return {"intel_summary": brief}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
