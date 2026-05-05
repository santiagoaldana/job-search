"""Daily brief router — priority-ordered action list for today."""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.database import get_session

router = APIRouter()


@router.get("")
def get_daily_brief(session: Session = Depends(get_session)):
    """Return the ordered list of actions for today."""
    from app.services.daily_brief import compute_daily_brief
    return compute_daily_brief(session)


class DismissRequest(BaseModel):
    action_type: str
    payload_id: Optional[int] = None


@router.post("/dismiss")
def dismiss_action(req: DismissRequest, session: Session = Depends(get_session)):
    """Permanently dismiss a brief action so it never appears again."""
    from app.models import DismissedBriefAction
    from sqlmodel import select
    existing = session.exec(
        select(DismissedBriefAction).where(
            DismissedBriefAction.action_type == req.action_type,
            DismissedBriefAction.payload_id == req.payload_id,
        )
    ).first()
    if not existing:
        session.add(DismissedBriefAction(action_type=req.action_type, payload_id=req.payload_id))
        session.commit()
    return {"dismissed": True}


class ApproveRequest(BaseModel):
    motivation: int = 7


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: int, req: ApproveRequest = ApproveRequest(), session: Session = Depends(get_session)):
    """Approve an AI-suggested company — enters active funnel with chosen motivation."""
    from app.models import AITargetSuggestion, Company

    suggestion = session.get(AITargetSuggestion, suggestion_id)
    if not suggestion:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Suggestion not found")

    motivation = max(1, min(10, req.motivation))
    company = Company(
        name=suggestion.name,
        motivation=motivation,
        funding_stage=suggestion.funding_stage or "unknown",
        is_archived=False,
        suggested_by_ai=True,
        stage="pool",
        lamp_score=round(motivation * 0.5 + 1.0 * 0.3 + 1.0 * 0.2, 2),
    )
    session.add(company)
    session.flush()

    suggestion.reviewed = True
    suggestion.approved = True
    suggestion.company_id = company.id
    session.add(suggestion)
    session.commit()
    return {"approved": True, "company_id": company.id, "company_name": company.name}


@router.post("/suggestions/{suggestion_id}/skip")
def skip_suggestion(suggestion_id: int, session: Session = Depends(get_session)):
    """Skip (dismiss) an AI-suggested company."""
    from app.models import AITargetSuggestion

    suggestion = session.get(AITargetSuggestion, suggestion_id)
    if not suggestion:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.reviewed = True
    suggestion.approved = False
    session.add(suggestion)
    session.commit()
    return {"skipped": True}


@router.post("/run-discovery")
async def run_discovery():
    """Trigger the weekly Series B/C startup discovery now."""
    try:
        from app.services.startup_discovery import run_discovery as _run
        await _run()
        return {"status": "done"}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
def pending_suggestions(session: Session = Depends(get_session)):
    """Return AI company suggestions not yet reviewed."""
    from app.models import AITargetSuggestion
    from sqlmodel import select
    suggestions = session.exec(
        select(AITargetSuggestion).where(AITargetSuggestion.reviewed == False)
    ).all()
    return suggestions
