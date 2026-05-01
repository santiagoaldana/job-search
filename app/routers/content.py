"""Content router — LinkedIn post drafts, scheduling, and publishing."""

import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import ContentDraft, ContentFeed

router = APIRouter()


class DraftAction(BaseModel):
    status: str  # approved | discarded | scheduled | published | pending
    scheduled_at: Optional[str] = None  # ISO datetime, used when status=scheduled
    body: Optional[str] = None  # direct body edit


@router.get("")
def list_drafts(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(ContentDraft).where(
        (ContentDraft.content_type == "linkedin") | (ContentDraft.content_type == None)
    )
    if status:
        q = q.where(ContentDraft.status == status)
    else:
        q = q.where(ContentDraft.status.in_(["pending", "approved", "scheduled"]))
    return session.exec(q.order_by(ContentDraft.net_score.desc())).all()


@router.get("/published")
def list_published(session: Session = Depends(get_session)):
    """Return last 10 published posts, newest first."""
    q = select(ContentDraft).where(ContentDraft.status == "published").order_by(ContentDraft.published_at.desc())
    return session.exec(q.limit(10)).all()


class GenerateRequest(BaseModel):
    days: int = 7
    count: int = 5


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


# ── LinkedIn OAuth ─────────────────────────────────────────────────────────────

@router.get("/linkedin/status")
def linkedin_status():
    """Return LinkedIn connection status."""
    try:
        from skills.linkedin_engine import get_auth_status
        return get_auth_status()
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.post("/linkedin/connect")
def linkedin_connect():
    """Return the LinkedIn OAuth URL for the user to visit."""
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set in .env. "
                   "Create an app at https://www.linkedin.com/developers/apps/new with the "
                   "'Share on LinkedIn' product and set redirect URI to http://localhost:8000/linkedin/callback",
        )
    import secrets
    from urllib.parse import urlencode
    state = secrets.token_urlsafe(16)
    # Store state in a simple file so callback can verify it
    state_path = os.path.expanduser("~/.job-search-linkedin/oauth_state")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        f.write(state)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "http://localhost:8000/linkedin/callback",
        "state": state,
        "scope": "w_member_social r_liteprofile openid profile",
    }
    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    return {"auth_url": auth_url}


# ── Scheduling ─────────────────────────────────────────────────────────────────

@router.get("/linkedin/next-slot")
def next_slot():
    """Return the next optimal posting slot (Wed/Thu 3-5 PM ET)."""
    try:
        from skills.linkedin_engine import next_optimal_slot
        slot = next_optimal_slot()
        return {"scheduled_at": slot.isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Publishing ─────────────────────────────────────────────────────────────────

@router.post("/{draft_id}/publish-now")
def publish_now(draft_id: int, session: Session = Depends(get_session)):
    """Immediately publish a draft to LinkedIn."""
    draft = session.get(ContentDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    try:
        from skills.linkedin_engine import _get_valid_token, publish_post, LinkedInDraftPost
        token = _get_valid_token()
        li_draft = LinkedInDraftPost(
            draft_id=str(draft.id),
            type="post",
            status="scheduled",
            body=draft.body,
        )
        post_id = publish_post(li_draft, token)
        draft.status = "published"
        draft.published_at = datetime.utcnow().isoformat()
        session.add(draft)
        session.commit()
        session.refresh(draft)
        return {"published": True, "linkedin_post_id": post_id, "draft": draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/linkedin/run-cycle")
def run_publish_cycle(session: Session = Depends(get_session)):
    """Publish all scheduled drafts whose time has arrived."""
    try:
        from skills.linkedin_engine import _get_valid_token, publish_post, LinkedInDraftPost
        token = _get_valid_token()
    except Exception as e:
        return {"skipped": True, "reason": str(e), "published": 0}

    now = datetime.utcnow().isoformat()
    due = session.exec(
        select(ContentDraft).where(
            ContentDraft.status == "scheduled",
            ContentDraft.scheduled_at <= now,
        )
    ).all()

    published = []
    errors = []
    for draft in due:
        try:
            li_draft = LinkedInDraftPost(
                draft_id=str(draft.id),
                type="post",
                status="scheduled",
                body=draft.body,
            )
            post_id = publish_post(li_draft, token)
            draft.status = "published"
            draft.published_at = datetime.utcnow().isoformat()
            session.add(draft)
            published.append({"id": draft.id, "linkedin_post_id": post_id})
        except Exception as e:
            errors.append({"id": draft.id, "error": str(e)})

    session.commit()
    return {"published": len(published), "errors": errors, "details": published}


# ── Feed management ────────────────────────────────────────────────────────────

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


# ── Substack ───────────────────────────────────────────────────────────────────

class SubstackGenerateRequest(BaseModel):
    topic: str
    count: int = 1


@router.post("/substack/generate")
async def generate_substack(req: SubstackGenerateRequest):
    """Generate Substack newsletter draft(s) via Claude Opus."""
    results = []
    for _ in range(req.count):
        try:
            from app.services.content_generator import generate_substack_draft
            draft = await generate_substack_draft(req.topic)
            results.append(draft)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"generated": len(results), "drafts": results}


@router.get("/substack")
def list_substack_drafts(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(ContentDraft).where(ContentDraft.content_type == "substack")
    if status:
        q = q.where(ContentDraft.status == status)
    else:
        q = q.where(ContentDraft.status.in_(["pending", "approved"]))
    return session.exec(q.order_by(ContentDraft.created_at.desc())).all()


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
    if action.status == "scheduled" and action.scheduled_at:
        draft.scheduled_at = action.scheduled_at
    if action.body is not None:
        draft.body = action.body
    session.add(draft)
    session.commit()
    return draft
