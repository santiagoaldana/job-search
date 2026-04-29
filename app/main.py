"""
Job Search System v2 — FastAPI entry point.

Run: uvicorn app.main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env before anything else
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import create_tables, run_migrations

# ── Scheduled jobs ────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()


async def job_refresh_leads():
    """Scrape career pages for active LAMP companies and fit-score new postings."""
    try:
        from app.services.career_scraper import refresh_active_companies
        await refresh_active_companies()
    except Exception as e:
        print(f"[scheduler] refresh_leads error: {e}")


async def job_daily_morning():
    """Daily 7am: pre-compute brief, flag events this week needing prep."""
    try:
        from app.database import engine
        from sqlmodel import Session
        from app.services.daily_brief import compute_daily_brief
        with Session(engine) as session:
            brief = compute_daily_brief(session)
        print(f"[7am] Daily brief ready: {brief['total_actions']} actions, {brief['overdue_count']} overdue")
    except Exception as e:
        print(f"[scheduler] daily_morning error: {e}")


async def job_weekly_digest():
    """Monday 8am: rebuild LAMP scores + send weekly email digest."""
    try:
        from app.services.startup_discovery import run_discovery
        await run_discovery()
    except Exception as e:
        print(f"[scheduler] weekly_digest error: {e}")


async def job_startup_discovery():
    """Weekly: surface new Series B/C targets via Claude."""
    try:
        from app.services.startup_discovery import run_discovery
        await run_discovery()
    except Exception as e:
        print(f"[scheduler] startup_discovery error: {e}")


async def job_linkedin_publish():
    """Every 30 min: publish scheduled LinkedIn posts whose time has arrived."""
    try:
        from app.database import engine
        from app.models import ContentDraft
        from datetime import datetime
        from sqlmodel import Session, select
        from skills.linkedin_engine import _get_valid_token, publish_post, LinkedInDraftPost
        try:
            token = _get_valid_token()
        except Exception:
            return  # Not connected yet — skip silently

        now = datetime.utcnow().isoformat()
        with Session(engine) as session:
            due = session.exec(
                select(ContentDraft).where(
                    ContentDraft.status == "scheduled",
                    ContentDraft.scheduled_at <= now,
                )
            ).all()
            for draft in due:
                try:
                    li_draft = LinkedInDraftPost(
                        draft_id=str(draft.id),
                        type="post",
                        status="scheduled",
                        body=draft.body,
                    )
                    publish_post(li_draft, token)
                    draft.status = "published"
                    draft.published_at = datetime.utcnow().isoformat()
                    session.add(draft)
                    print(f"[linkedin] Published draft {draft.id}")
                except Exception as e:
                    print(f"[linkedin] Failed to publish draft {draft.id}: {e}")
            session.commit()
    except Exception as e:
        print(f"[scheduler] linkedin_publish error: {e}")


# ── App lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    run_migrations()
    try:
        from app.migrate import seed_feeds
        from sqlmodel import Session
        from app.database import engine
        with Session(engine) as session:
            seed_feeds(session)
    except Exception as e:
        print(f"[startup] seed_feeds error: {e}")

    # Every 6 hours: refresh leads for active companies
    scheduler.add_job(
        job_refresh_leads,
        IntervalTrigger(hours=6),
        id="refresh_leads",
        replace_existing=True,
    )
    # Daily 7am: daily brief pre-computation + event reminder check
    scheduler.add_job(
        job_daily_morning,
        CronTrigger(hour=7, minute=0),
        id="daily_morning",
        replace_existing=True,
    )
    # Monday 7am: weekly digest
    scheduler.add_job(
        job_weekly_digest,
        CronTrigger(day_of_week="mon", hour=7),
        id="weekly_digest",
        replace_existing=True,
    )
    # Sunday 7am: startup discovery
    scheduler.add_job(
        job_startup_discovery,
        CronTrigger(day_of_week="sun", hour=7),
        id="startup_discovery",
        replace_existing=True,
    )
    # Every 30 min: publish scheduled LinkedIn posts
    scheduler.add_job(
        job_linkedin_publish,
        IntervalTrigger(minutes=30),
        id="linkedin_publish",
        replace_existing=True,
    )

    scheduler.start()
    print("✓ Job Search System v2 started")
    yield
    scheduler.shutdown()


# ── App instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Job Search System v2",
    description="Santiago Aldana's executive job search automation",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth middleware ───────────────────────────────────────────────────────────

PUBLIC_PATHS = {"/api/health", "/auth/login", "/auth/callback", "/auth/logout", "/auth/me", "/linkedin/callback"}

@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    # Allow public paths and static assets
    if path in PUBLIC_PATHS or path.startswith("/assets/"):
        return await call_next(request)
    # Allow API calls only if authenticated
    if path.startswith("/api/"):
        # MCP server bypass — trusted caller identified by shared secret
        mcp_secret = os.environ.get("MCP_SECRET", "")
        if mcp_secret and request.headers.get("X-MCP-Secret") == mcp_secret:
            return await call_next(request)
        from app.routers.auth import get_session_email
        if not get_session_email(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────

from app.routers import companies, leads, outreach, cv, applications, events, content, daily_brief, contacts
from app.routers.auth import router as auth_router


@app.get("/linkedin/callback", include_in_schema=False)
async def linkedin_oauth_callback(code: str = None, state: str = None, error: str = None):
    """Handle LinkedIn OAuth2 callback, exchange code for token."""
    if error:
        return JSONResponse({"detail": f"LinkedIn auth error: {error}"}, status_code=400)
    if not code:
        return JSONResponse({"detail": "No authorization code received"}, status_code=400)

    # Verify state
    state_path = os.path.expanduser("~/.job-search-linkedin/oauth_state")
    try:
        with open(state_path) as f:
            expected_state = f.read().strip()
        if state != expected_state:
            return JSONResponse({"detail": "CSRF state mismatch"}, status_code=400)
    except FileNotFoundError:
        pass  # Skip CSRF check if state file missing

    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

    import httpx
    import json
    from datetime import timedelta

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost:8000/linkedin/callback",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not resp.is_success:
            return JSONResponse({"detail": f"Token exchange failed: {resp.text}"}, status_code=400)
        token_data = resp.json()

        # Fetch person URN and name
        profile_resp = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        profile = profile_resp.json() if profile_resp.is_success else {}

    from datetime import datetime
    expires_at = (datetime.now() + timedelta(seconds=token_data.get("expires_in", 5184000))).isoformat()
    token = {
        "access_token": token_data["access_token"],
        "expires_at": expires_at,
        "person_urn": f"urn:li:person:{profile.get('sub', '')}",
        "person_name": profile.get("name", ""),
        "person_id": profile.get("sub", ""),
    }

    token_dir = os.path.expanduser("~/.job-search-linkedin")
    os.makedirs(token_dir, exist_ok=True)
    with open(os.path.join(token_dir, "token.json"), "w") as f:
        json.dump(token, f, indent=2)

    name = token.get("person_name", "you")
    return JSONResponse({
        "connected": True,
        "person_name": name,
        "expires_at": expires_at[:10],
        "message": f"LinkedIn connected as {name}. You can close this tab.",
    })

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
app.include_router(outreach.router, prefix="/api/outreach", tags=["outreach"])
app.include_router(contacts.router, prefix="/api/contacts", tags=["contacts"])
app.include_router(cv.router, prefix="/api/cv", tags=["cv"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(daily_brief.router, prefix="/api/daily-brief", tags=["daily-brief"])


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ── Static frontend (built React app) ─────────────────────────────────────────
# Served after all API routes so /api/* is never caught by StaticFiles.

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_DIST = Path(__file__).parent.parent / "web" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        return FileResponse(_DIST / "index.html")
