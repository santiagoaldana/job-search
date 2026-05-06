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
    """Daily 7am: Gmail sync then pre-compute brief."""
    try:
        from app.database import engine
        from sqlmodel import Session
        from app.services.gmail_sync_service import run_gmail_sync
        from app.services.daily_brief import compute_daily_brief
        with Session(engine) as session:
            sync_result = run_gmail_sync(session)
            print(f"[gmail_sync] {sync_result}")
            brief = compute_daily_brief(session)
        print(f"[7am] Daily brief ready: {brief['total_actions']} actions, {brief['overdue_count']} overdue")
    except Exception as e:
        print(f"[scheduler] daily_morning error: {e}")



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

    try:
        from app.services.gmail_sync_service import _bootstrap_token, _persist_token, GMAIL_ACCOUNT
        from app.models import GmailSyncState
        from sqlmodel import Session, select
        from app.database import engine
        with Session(engine) as session:
            state = session.exec(
                select(GmailSyncState).where(GmailSyncState.account_email == GMAIL_ACCOUNT)
            ).first()
            if not state or not state.gmail_token_json:
                # Seed DB from env var on first deploy
                _bootstrap_token(None)   # writes env var token to disk
                _persist_token(session)  # reads disk → writes to DB
                print("[startup] Gmail token seeded into DB from env var")
            else:
                print("[startup] Gmail token already in DB — skipping seed")
    except Exception as e:
        print(f"[startup] Gmail token seed error: {e}")

    # Wed + Sat 8am: refresh leads for active companies (was every 6 hours)
    scheduler.add_job(
        job_refresh_leads,
        CronTrigger(day_of_week="wed,sat", hour=8),
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
    # 7:45am and 12:45pm daily: publish scheduled LinkedIn posts (was every 30 min)
    scheduler.add_job(
        job_linkedin_publish,
        CronTrigger(hour="7,12", minute=45),
        id="linkedin_publish",
        replace_existing=True,
    )

    scheduler.start()

    # Keep-alive: ping self every 4 min to prevent Render free-tier cold starts
    import threading, urllib.request, time
    _api_url = os.environ.get("API_BASE_URL", "https://job-search-do1r.onrender.com")
    def _keep_alive():
        while True:
            time.sleep(240)
            try:
                urllib.request.urlopen(f"{_api_url}/api/health", timeout=10)
            except Exception:
                pass
    threading.Thread(target=_keep_alive, daemon=True).start()

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

PUBLIC_PATHS = {"/api/health", "/auth/login", "/auth/callback", "/auth/logout", "/auth/me", "/linkedin/callback", "/mcp-sse"}

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


# ── MCP SSE proxy ─────────────────────────────────────────────────────────────
# Forwards /mcp-sse and /mcp-messages/* to the local MCP HTTP server on port 8080.
# This lets Claude.ai reach the MCP server through the existing cloudflared tunnel
# (jobsearch.aidatasolutions.co) without needing a separate subdomain or SSL cert.

from fastapi import Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

MCP_LOCAL = "http://localhost:8080"

@app.api_route("/mcp-sse", methods=["GET"], include_in_schema=False)
async def mcp_sse_proxy(request: Request):
    async with httpx.AsyncClient(timeout=None) as client:
        req = client.build_request("GET", f"{MCP_LOCAL}/sse", headers=dict(request.headers))
        resp = await client.send(req, stream=True)
        return StreamingResponse(
            resp.aiter_raw(),
            status_code=resp.status_code,
            headers=dict(resp.headers),
            background=BackgroundTask(resp.aclose),
        )

@app.api_route("/mcp-messages/{path:path}", methods=["POST"], include_in_schema=False)
async def mcp_messages_proxy(request: Request, path: str):
    body = await request.body()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{MCP_LOCAL}/mcp-messages/{path}",
            content=body,
            headers=dict(request.headers),
            params=dict(request.query_params),
        )
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


# ── Routers ───────────────────────────────────────────────────────────────────

from app.routers import companies, leads, outreach, cv, applications, events, content, daily_brief, contacts, reports, references, gmail_sync, strategy
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
                "redirect_uri": "https://job-search-do1r.onrender.com/linkedin/callback",
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
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(references.router, prefix="/api/references", tags=["references"])
app.include_router(gmail_sync.router, prefix="/api/gmail", tags=["gmail"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])


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
