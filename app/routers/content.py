"""Content router — LinkedIn post drafts."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import ContentDraft, ContentFeed

router = APIRouter()


class DraftAction(BaseModel):
    status: str  # approved | discarded | scheduled


@router.get("")
def list_drafts(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(ContentDraft)
    if status:
        q = q.where(ContentDraft.status == status)
    else:
        q = q.where(ContentDraft.status.in_(["pending", "approved", "scheduled"]))
    return session.exec(q.order_by(ContentDraft.net_score.desc())).all()


class GenerateRequest(BaseModel):
    days: int = 7
    count: int = 3


@router.post("/generate")
async def generate_drafts(req: GenerateRequest = GenerateRequest()):
    """Pull FinTech news and generate LinkedIn post drafts via Claude Opus."""
    try:
        from app.services.content_generator import generate_linkedin_drafts
        drafts = await generate_linkedin_drafts(days=req.days, count=req.count)
        return {"generated": len(drafts), "drafts": drafts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ComposeRequest(BaseModel):
    context: str


@router.post("/compose")
async def compose_draft(req: ComposeRequest, session: Session = Depends(get_session)):
    """Generate a LinkedIn post from Santiago's own topic/context."""
    try:
        from app.services.content_generator import compose_linkedin_post
        body, net_score, controversy, risk = await compose_linkedin_post(req.context)
        draft = ContentDraft(
            source_title=req.context[:120],
            body=body,
            net_score=net_score,
            controversy_score=controversy,
            risk_score=risk,
            status="pending",
        )
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RegenerateRequest(BaseModel):
    instructions: str


@router.post("/{draft_id}/regenerate")
async def regenerate_draft(
    draft_id: int,
    req: RegenerateRequest,
    session: Session = Depends(get_session),
):
    """Regenerate a draft with natural language edit instructions."""
    draft = session.get(ContentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    try:
        from app.services.content_generator import regenerate_linkedin_draft
        new_body, new_score = await regenerate_linkedin_draft(
            original_body=draft.body,
            source_title=draft.source_title or "",
            instructions=req.instructions,
        )
        draft.body = new_body
        draft.net_score = new_score
        draft.status = "pending"
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return draft
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FeedCreate(BaseModel):
    name: str
    url: str
    category: str = "publication"


@router.get("/feeds")
def list_feeds(session: Session = Depends(get_session)):
    return session.exec(select(ContentFeed).where(ContentFeed.active == True).order_by(ContentFeed.category, ContentFeed.name)).all()


@router.post("/feeds")
def add_feed(data: FeedCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(ContentFeed).where(ContentFeed.url == data.url)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Feed URL already exists")
    feed = ContentFeed(name=data.name, url=data.url, category=data.category)
    session.add(feed)
    session.commit()
    session.refresh(feed)
    return feed


@router.delete("/feeds/{feed_id}")
def delete_feed(feed_id: int, session: Session = Depends(get_session)):
    feed = session.get(ContentFeed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    session.delete(feed)
    session.commit()
    return {"deleted": feed_id}


@router.patch("/{draft_id}")
def update_draft(
    draft_id: int,
    action: DraftAction,
    session: Session = Depends(get_session),
):
    draft = session.get(ContentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    valid = {"approved", "discarded", "scheduled", "published", "pending"}
    if action.status not in valid:
        raise HTTPException(status_code=400, detail="Invalid status")
    draft.status = action.status
    session.add(draft)
    session.commit()
    return draft
