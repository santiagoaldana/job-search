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

from app.database import create_tables

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


# ── App lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
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

PUBLIC_PATHS = {"/api/health", "/auth/login", "/auth/callback", "/auth/logout", "/auth/me"}

@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    # Allow public paths and static assets
    if path in PUBLIC_PATHS or path.startswith("/assets/"):
        return await call_next(request)
    # Allow API calls only if authenticated
    if path.startswith("/api/"):
        from app.routers.auth import get_session_email
        if not get_session_email(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────

from app.routers import companies, leads, outreach, cv, applications, events, content, daily_brief
from app.routers.auth import router as auth_router

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
app.include_router(outreach.router, prefix="/api/outreach", tags=["outreach"])
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
