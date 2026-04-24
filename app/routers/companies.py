"""Companies router — LAMP list CRUD, stage transitions, intel refresh."""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
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
    org_notes: Optional[str] = None


class CompanyCreate(BaseModel):
    name: str
    motivation: int = 7
    funding_stage: str = "unknown"
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


@router.get("/funnel")
def funnel_view(session: Session = Depends(get_session)):
    """Return active companies grouped by funnel stage."""
    companies = session.exec(
        select(Company)
        .where(Company.is_archived == False, Company.motivation >= 7)
        .order_by(Company.lamp_score.desc())
    ).all()

    stages = ["pool", "researched", "outreach", "response", "meeting",
              "applied", "interview", "offer", "closed"]
    result = {s: [] for s in stages}
    for c in companies:
        bucket = c.stage if c.stage in result else "pool"
        result[bucket].append({
            "id": c.id,
            "name": c.name,
            "lamp_score": c.lamp_score,
            "motivation": c.motivation,
            "funding_stage": c.funding_stage,
            "stage": c.stage,
            "intel_summary": c.intel_summary,
        })
    return result


@router.get("/{company_id}")
def get_company(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    contacts = session.exec(
        select(Contact).where(Contact.company_id == company_id)
    ).all()
    leads = session.exec(
        select(Lead).where(Lead.company_id == company_id, Lead.status == "active")
        .order_by(Lead.fit_score.desc())
    ).all()
    outreach = session.exec(
        select(OutreachRecord).where(OutreachRecord.company_id == company_id)
        .order_by(OutreachRecord.sent_at.desc())
    ).all()
    applications = session.exec(
        select(Application).where(Application.company_id == company_id)
    ).all()

    return {
        "company": company,
        "contacts": contacts,
        "leads": leads,
        "outreach": outreach,
        "applications": applications,
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


@router.post("/{company_id}/stage")
def set_stage(
    company_id: int,
    stage: str,
    session: Session = Depends(get_session),
):
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


@router.post("")
def create_company(data: CompanyCreate, session: Session = Depends(get_session)):
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
