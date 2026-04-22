"""Applications router — lifecycle from draft to submitted."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Application, Company, Lead, Interview, Offer

router = APIRouter()


class ApplicationCreate(BaseModel):
    company_id: int
    lead_id: int
    cv_version_path: Optional[str] = None
    cover_notes: Optional[str] = None


class InterviewCreate(BaseModel):
    scheduled_at: str
    type: str = "video"
    interviewer_name: Optional[str] = None
    prep_notes: Optional[str] = None


class OfferCreate(BaseModel):
    received_date: Optional[str] = None
    title: Optional[str] = None
    salary: Optional[str] = None
    equity: Optional[str] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
def list_applications(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(Application)
    if status:
        q = q.where(Application.status == status)
    apps = session.exec(q.order_by(Application.created_at.desc())).all()
    result = []
    for app in apps:
        company = session.get(Company, app.company_id) if app.company_id else None
        lead = session.get(Lead, app.lead_id) if app.lead_id else None
        result.append({
            **app.dict(),
            "company_name": company.name if company else "Unknown",
            "lead_title": lead.title if lead else "Unknown",
        })
    return result


@router.post("")
def create_application(data: ApplicationCreate, session: Session = Depends(get_session)):
    app = Application(
        company_id=data.company_id,
        lead_id=data.lead_id,
        cv_version_path=data.cv_version_path,
        cover_notes=data.cover_notes,
        status="draft",
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


@router.get("/{app_id}")
def get_application(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    interviews = session.exec(
        select(Interview).where(Interview.application_id == app_id)
    ).all()
    offers = session.exec(
        select(Offer).where(Offer.application_id == app_id)
    ).all()
    return {**app.dict(), "interviews": interviews, "offers": offers}


@router.patch("/{app_id}/status")
def update_status(
    app_id: int,
    status: str,
    session: Session = Depends(get_session),
):
    valid = {"draft", "pending_review", "approved", "submitted",
             "screen", "interview", "offer", "rejected", "withdrawn"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app.status = status
    app.updated_at = datetime.utcnow().isoformat()

    if status == "submitted":
        app.applied_date = datetime.utcnow().strftime("%Y-%m-%d")
        # Move company to applied stage
        if app.company_id:
            company = session.get(Company, app.company_id)
            if company:
                company.stage = "applied"
                company.updated_at = datetime.utcnow().isoformat()
                session.add(company)

    session.add(app)
    session.commit()
    return app


@router.post("/{app_id}/submit")
async def submit_application(app_id: int, session: Session = Depends(get_session)):
    """Launch Playwright to pre-fill and submit the application."""
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status not in ("approved", "pending_review"):
        raise HTTPException(
            status_code=400,
            detail=f"Application must be approved before submitting (current: {app.status})"
        )

    lead = session.get(Lead, app.lead_id) if app.lead_id else None
    if not lead or not lead.url:
        raise HTTPException(status_code=400, detail="Lead has no application URL")

    try:
        from app.services.application_engine import launch_application
        result = await launch_application(
            application=app,
            apply_url=lead.url,
            cv_version_path=app.cv_version_path,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{app_id}/interviews")
def add_interview(
    app_id: int,
    data: InterviewCreate,
    session: Session = Depends(get_session),
):
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    interview = Interview(
        application_id=app_id,
        scheduled_at=data.scheduled_at,
        type=data.type,
        interviewer_name=data.interviewer_name,
        prep_notes=data.prep_notes,
    )
    app.status = "interview"
    app.updated_at = datetime.utcnow().isoformat()

    if app.company_id:
        company = session.get(Company, app.company_id)
        if company:
            company.stage = "interview"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    session.add(interview)
    session.add(app)
    session.commit()
    session.refresh(interview)
    return interview


@router.post("/{app_id}/offers")
def add_offer(
    app_id: int,
    data: OfferCreate,
    session: Session = Depends(get_session),
):
    app = session.get(Application, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    offer = Offer(
        application_id=app_id,
        received_date=data.received_date,
        title=data.title,
        salary=data.salary,
        equity=data.equity,
        start_date=data.start_date,
        notes=data.notes,
        decision="pending",
    )
    app.status = "offer"
    app.updated_at = datetime.utcnow().isoformat()

    if app.company_id:
        company = session.get(Company, app.company_id)
        if company:
            company.stage = "offer"
            company.updated_at = datetime.utcnow().isoformat()
            session.add(company)

    session.add(offer)
    session.add(app)
    session.commit()
    session.refresh(offer)
    return offer
