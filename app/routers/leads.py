"""Leads router — job opportunities, fit scoring, scrape refresh."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlmodel import Session, select

from app.database import get_session
from app.models import Lead, Company

router = APIRouter()


@router.get("")
def list_leads(
    min_fit: Optional[float] = Query(None, description="Minimum fit score 0-100"),
    location_compatible: Optional[bool] = Query(None),
    status: str = Query("active"),
    company_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
):
    q = select(Lead).where(Lead.status == status)
    if min_fit is not None:
        q = q.where(Lead.fit_score >= min_fit)
    if location_compatible is not None:
        q = q.where(Lead.location_compatible == location_compatible)
    if company_id is not None:
        q = q.where(Lead.company_id == company_id)

    leads = session.exec(q).all()

    # Enrich with company name and sort by lamp_score desc, then company name asc
    result = []
    for lead in leads:
        company = session.get(Company, lead.company_id) if lead.company_id else None
        result.append({
            **lead.dict(),
            "company_name": company.name if company else "Unknown",
            "_lamp_score": company.lamp_score if company else 0,
        })
    result.sort(key=lambda x: (-x["_lamp_score"], x["company_name"].lower()))
    for r in result:
        del r["_lamp_score"]
    return result


@router.get("/hot")
def hot_leads(session: Session = Depends(get_session)):
    """Leads with fit_score ≥ 65 and location_compatible=True."""
    leads = session.exec(
        select(Lead)
        .where(Lead.fit_score >= 65, Lead.location_compatible == True, Lead.status == "active")
        .order_by(Lead.fit_score.desc())
    ).all()
    result = []
    for lead in leads:
        company = session.get(Company, lead.company_id) if lead.company_id else None
        result.append({**lead.dict(), "company_name": company.name if company else "Unknown"})
    return result


@router.get("/{lead_id}")
def get_lead(lead_id: int, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    company = session.get(Company, lead.company_id) if lead.company_id else None
    return {**lead.dict(), "company_name": company.name if company else "Unknown"}


@router.post("/refresh")
async def refresh_leads(
    background_tasks: BackgroundTasks,
    company_id: Optional[int] = Query(None, description="Refresh specific company only"),
    session: Session = Depends(get_session),
):
    """Trigger career page scrape + fit scoring. Runs in background."""
    try:
        from app.services.career_scraper import refresh_active_companies, refresh_company
        if company_id:
            company = session.get(Company, company_id)
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
            background_tasks.add_task(refresh_company, company)
            return {"status": "started", "company": company.name}
        else:
            background_tasks.add_task(refresh_active_companies)
            return {"status": "started", "message": "Refreshing all active companies"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{lead_id}/score")
async def score_lead(lead_id: int, session: Session = Depends(get_session)):
    """(Re)score a specific lead against Santiago's profile."""
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    try:
        from app.services.fit_scorer import score_lead as _score
        result = await _score(lead)
        lead.fit_score = result["fit_score"]
        lead.fit_strengths = str(result["fit_strengths"])
        lead.fit_gaps = str(result["fit_gaps"])
        lead.location_compatible = result["location_compatible"]
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return lead
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{lead_id}/fetch-jd")
async def fetch_full_jd(lead_id: int, session: Session = Depends(get_session)):
    """Scrape the full job description from the posting URL and store it."""
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.url:
        raise HTTPException(status_code=400, detail="Lead has no URL")
    try:
        import httpx
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            r = await client.get(lead.url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())[:8000]
        lead.description = text
        session.add(lead)
        session.commit()
        return {"ok": True, "length": len(text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{lead_id}/status")
def update_lead_status(
    lead_id: int,
    status: str,
    session: Session = Depends(get_session),
):
    valid = {"active", "applied", "closed"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = status
    session.add(lead)
    session.commit()
    return {"id": lead_id, "status": status}
