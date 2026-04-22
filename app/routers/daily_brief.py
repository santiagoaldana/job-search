"""Daily brief router — priority-ordered action list for today."""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session

router = APIRouter()


@router.get("")
def get_daily_brief(session: Session = Depends(get_session)):
    """Return the ordered list of actions for today."""
    from app.services.daily_brief import compute_daily_brief
    return compute_daily_brief(session)


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(suggestion_id: int, session: Session = Depends(get_session)):
    """Approve an AI-suggested company — enters active funnel at motivation 7."""
    from app.models import AITargetSuggestion, Company
    from datetime import datetime

    suggestion = session.get(AITargetSuggestion, suggestion_id)
    if not suggestion:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Create company if not already exists
    company = Company(
        name=suggestion.name,
        motivation=7,
        funding_stage=suggestion.funding_stage or "unknown",
        is_archived=False,
        suggested_by_ai=True,
        stage="pool",
        lamp_score=round(7 * 0.5 + 1.0 * 0.3 + 1.0 * 0.2, 2),
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
