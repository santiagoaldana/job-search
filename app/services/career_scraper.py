"""
Career Site Scraper — zero cost job discovery for LAMP companies.
Tier 1: Greenhouse API (no auth)
Tier 2: Lever API (no auth)
Tier 3: Direct career page scrape (httpx + BeautifulSoup)
"""

import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent.parent.parent
CAREER_URLS_PATH = BASE_DIR / "data" / "career_urls.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15


def _load_career_urls() -> dict:
    if CAREER_URLS_PATH.exists():
        return json.loads(CAREER_URLS_PATH.read_text())
    return {}


async def fetch_greenhouse_jobs(slug: str) -> list:
    """Fetch jobs from Greenhouse public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs", [])
            return [
                {
                    "title": j.get("title", ""),
                    "url": j.get("absolute_url", ""),
                    "location": j.get("location", {}).get("name", ""),
                    "posted_date": j.get("updated_at", "")[:10] if j.get("updated_at") else None,
                    "source": "greenhouse",
                    "description": "",
                }
                for j in jobs
            ]
        except Exception:
            return []


async def fetch_lever_jobs(slug: str) -> list:
    """Fetch jobs from Lever public API."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            jobs = resp.json()
            if not isinstance(jobs, list):
                return []
            return [
                {
                    "title": j.get("text", ""),
                    "url": j.get("hostedUrl", ""),
                    "location": j.get("categories", {}).get("location", ""),
                    "posted_date": datetime.fromtimestamp(
                        j["createdAt"] / 1000
                    ).strftime("%Y-%m-%d") if j.get("createdAt") else None,
                    "source": "lever",
                    "description": BeautifulSoup(
                        j.get("descriptionPlain", ""), "html.parser"
                    ).get_text()[:500],
                }
                for j in jobs
            ]
        except Exception:
            return []


async def scrape_career_page(url: str) -> list:
    """Scrape a direct career page and extract job listings."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return []

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []

    # Try common job listing patterns
    # Pattern 1: <a> tags containing "job" or "position" text near a heading
    seen = set()
    for tag in soup.find_all(["a", "h2", "h3", "h4", "li"]):
        text = tag.get_text(strip=True)
        href = tag.get("href", "") if tag.name == "a" else ""
        if len(text) < 10 or len(text) > 200:
            continue
        # Filter for likely job titles (contain keywords)
        if not any(kw in text.lower() for kw in [
            "head of", "vp ", "vice president", "director", "manager",
            "chief", "officer", "lead ", "engineer", "product", "sales",
            "marketing", "analyst", "counsel", "operations", "growth"
        ]):
            continue
        if text in seen:
            continue
        seen.add(text)

        full_url = href
        if href and not href.startswith("http"):
            base = url.rstrip("/")
            full_url = f"{base}/{href.lstrip('/')}"

        jobs.append({
            "title": text,
            "url": full_url or url,
            "location": "",
            "posted_date": None,
            "source": "career_page",
            "description": "",
        })

    return jobs[:50]  # cap at 50 per page


async def get_company_jobs(company) -> list:
    """
    Fetch jobs for a company using the best available method.
    company: Company SQLModel instance
    """
    jobs = []

    if company.greenhouse_slug:
        jobs = await fetch_greenhouse_jobs(company.greenhouse_slug)
    elif company.lever_slug:
        jobs = await fetch_lever_jobs(company.lever_slug)
    else:
        career_urls = _load_career_urls()
        url = company.career_page_url or career_urls.get(company.name)
        if url:
            jobs = await scrape_career_page(url)
        else:
            # Try common patterns
            name_slug = re.sub(r"[^a-z0-9]", "", company.name.lower())
            for candidate in [
                f"https://{name_slug}.com/careers",
                f"https://{name_slug}.com/jobs",
                f"https://www.{name_slug}.com/careers",
            ]:
                jobs = await scrape_career_page(candidate)
                if jobs:
                    break

    return jobs


async def refresh_company(company) -> int:
    """
    Scrape a company's career page, fit-score new leads, save to DB.
    Returns count of new leads added.
    """
    from app.database import engine
    from sqlmodel import Session, select
    from app.models import Lead
    from app.services.fit_scorer import score_lead

    jobs = await get_company_jobs(company)
    if not jobs:
        return 0

    new_count = 0
    with Session(engine) as session:
        existing_urls = set(
            row[0] for row in session.exec(
                select(Lead.url).where(Lead.company_id == company.id)
            ).all()
        )

        for job in jobs:
            if job["url"] and job["url"] in existing_urls:
                continue

            lead = Lead(
                company_id=company.id,
                title=job["title"],
                url=job["url"] or None,
                location=job["location"] or None,
                description=job["description"] or None,
                status="active",
                source=job["source"],
                posted_date=job["posted_date"],
                fetched_date=datetime.utcnow().isoformat(),
            )

            # Fit-score immediately
            try:
                score = await score_lead(lead)
                lead.fit_score = score["fit_score"]
                lead.fit_strengths = json.dumps(score["fit_strengths"])
                lead.fit_gaps = json.dumps(score["fit_gaps"])
                lead.location_compatible = score["location_compatible"]
            except Exception:
                lead.location_compatible = True

            session.add(lead)
            new_count += 1

        session.commit()

    return new_count


async def refresh_active_companies():
    """Refresh leads for all active (non-archived, motivation ≥ 7) companies."""
    from app.database import engine
    from sqlmodel import Session, select
    from app.models import Company

    with Session(engine) as session:
        companies = session.exec(
            select(Company).where(
                Company.is_archived == False,
                Company.motivation >= 7,
            )
        ).all()

    print(f"[scraper] Refreshing {len(companies)} active companies…")
    total_new = 0
    for company in companies:
        try:
            new = await refresh_company(company)
            if new:
                print(f"  [scraper] {company.name}: +{new} leads")
            total_new += new
            await asyncio.sleep(1)  # polite delay between requests
        except Exception as e:
            print(f"  [scraper] {company.name} error: {e}")

    print(f"[scraper] Done. {total_new} new leads total.")
