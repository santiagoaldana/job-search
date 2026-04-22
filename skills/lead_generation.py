"""
Lead Generation Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Identifies C-suite and senior leadership openings across payments, embedded banking,
Agentic AI, and traditional banking innovation. Three fetch tiers:

  Tier 1 (always):  Greenhouse + Lever public APIs — no auth required
  Tier 2 (optional): Apify LinkedIn Jobs actor — requires APIFY_API_KEY
  Tier 3 (always):  Direct career page scraping for curated target companies

Connection proximity scoring uses LinkedIn contacts CSV export if provided.

Report tiers:
  HOT   (net ≥ 7.0): Apply immediately
  WARM  (net 5.0–6.9): Research + warm intro needed
  WATCH (net < 5.0): Monitor only

Usage:
  python3 -m skills.lead_generation
  python3 -m skills.lead_generation --contacts cv/contacts_export.csv
"""

import csv
import httpx
import json
import re
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
import anthropic

from skills.shared import (
    EXECUTIVE_PROFILE, MODEL_HAIKU, DATA_DIR, CONTACTS_CSV, compute_net_score
)

# ── Target Companies ──────────────────────────────────────────────────────────
#
# Bias toward growth-stage FinTech / payments / digital identity companies
# (Series B–D, 50–500 employees) where an operator with LATAM scale, digital
# identity expertise, and C-suite track record is genuinely differentiated.
# Boston-area or strong remote/hybrid preference.

# Greenhouse API slugs — companies using Greenhouse ATS
GREENHOUSE_SLUGS = [
    # Payments infrastructure & embedded finance (growth-stage)
    "lithic", "modern-treasury", "column", "unit", "synctera",
    "sardine", "alloy", "socure", "checkbook", "payitoff",
    "highnote", "apto-payments", "solid", "treasury-prime",
    # Digital identity & fraud / KYC
    "persona", "truework", "footprint", "auth0",
    # FinTech operators — Boston / NE region or strong remote
    "vestwell", "capitalize", "pinwheel", "spinwheel",
    # LATAM-origin companies expanding to US — Santiago's background is directly relevant
    "dlocal", "remitly", "ebanx", "pomelo", "clara", "tribal-credit",
    # Larger FinTech still worth watching
    "stripe", "marqeta", "checkout", "wise",
    "plaid", "synapse", "piermont",
]

# Lever API slugs
LEVER_SLUGS = [
    # Growth-stage payments / embedded banking
    "mercury", "relay", "found", "novo", "ramp", "brex",
    # Digital identity / compliance
    "hummingbird", "sentilink",
    # Boston-area FinTech
    "circle", "draft-kings",
    # LATAM-origin, US expanding
    "jeeves", "rapyd", "kushki",
]

# Direct career page targets (company name → careers URL)
# Prioritizes Boston-area companies and growth-stage FinTech not on Greenhouse/Lever
DIRECT_CAREER_PAGES = {
    # Boston / New England FinTech & financial services
    "Eastern Bank":         "https://www.easternbank.com/careers",
    "Citizens Bank":        "https://jobs.citizensbank.com/search-jobs",
    "Flywire":              "https://www.flywire.com/company/careers",
    "EzShield / Sontiq":    "https://www.sontiq.com/careers/",
    "Candex":               "https://www.candex.com/careers",
    "Actimize":             "https://www.niceactimize.com/about-us/careers.html",
    # Payments / embedded finance — growth stage, hybrid/remote-friendly
    "Nuvei":                "https://www.nuvei.com/en/careers",
    "Payoneer":             "https://payoneer.com/careers/",
    "Nymbus":               "https://nymbus.com/careers/",
    "Orum":                 "https://orum.io/careers",
    "Atomic":               "https://atomic.financial/careers",
    "Alviere":              "https://alviere.com/about/careers",
    "Banked":               "https://banked.com/careers",
    "Deposits":             "https://deposits.com/careers",
    # Digital identity / KYC / fraud — where LATAM+SoyYo cred is unique
    "Incode Technologies":  "https://incode.com/careers/",
    "Veriff":               "https://veriff.com/careers",
    "Onfido":               "https://onfido.com/about/careers/",
    "Idemia":               "https://www.idemia.com/careers",
    # Agentic AI / AI-native FinTech — emerging category Santiago targets
    "Sardine":              "https://www.sardine.ai/careers",
    "Finix":                "https://finix.com/careers",
    "Moov":                 "https://moov.io/careers/",
    "Slope":                "https://slope.so/careers",
    "Paysign":              "https://www.paysign.com/careers/",
    # Credit union technology vendors — SMCU role gives Santiago immediate domain credibility
    "Nymbus":               "https://nymbus.com/careers/",
    "Candescent":           "https://candescent.com/careers",
    "Bottomline":           "https://www.bottomline.com/us/about-us/careers",
    "Jack Henry":           "https://careers.jackhenry.com/",
    "Velera":               "https://careers.velera.com/",
    "Curql":                "https://curql.com/careers/",
}

# ── Title Patterns ────────────────────────────────────────────────────────────

TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"chief\s+(product|technology|revenue|operating|digital|innovation)\s+officer",
        r"(svp|evp|vp)\s+(of\s+)?(product|engineering|payments|growth|strategy|innovation|technology)",
        r"head\s+of\s+(payments|embedded\s+finance|banking|platform|product|innovation|digital)",
        r"(general\s+manager|managing\s+director).*(fintech|payments|banking|digital)",
        r"\b(president|coo|cto|cpo|cdo|ciso)\b",
        r"(director|vp|svp).*(payments|fintech|banking|identity|fraud)",
    ]
]


def _matches_title(title: str) -> bool:
    return any(p.search(title) for p in TITLE_PATTERNS)


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class JobLead:
    title: str
    company: str
    url: str
    location: str
    posted_date: str
    description_snippet: str
    source: str               # "greenhouse", "lever", "direct", "apify"
    utility: int              # 1-10
    risk: int                 # 1-10
    net_score: float
    connection_proximity: str # "1st", "2nd", "unknown"
    contact_name: str = ""    # 1st-degree contact at company if found
    tier: str = ""            # HOT / WARM / WATCH (set after scoring)
    fit_score: int = 0        # 0-100 CV-to-JD fit score
    fit_strengths: str = ""   # Key match points from JD analysis
    fit_gaps: str = ""        # Notable gaps vs JD requirements


# ── Greenhouse Fetcher ────────────────────────────────────────────────────────

def fetch_greenhouse_jobs(slugs: list[str] = GREENHOUSE_SLUGS) -> list[dict]:
    """Fetch jobs from Greenhouse public API. No auth required."""
    raw_jobs = []
    client = httpx.Client(timeout=10)
    for slug in slugs:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for job in data.get("jobs", []):
                    job["_company_slug"] = slug
                    raw_jobs.append(job)
        except Exception as e:
            print(f"[Lead Gen] Greenhouse error for '{slug}': {e}")
        time.sleep(0.3)
    client.close()
    print(f"[Lead Gen] Greenhouse: {len(raw_jobs)} total raw jobs")
    return raw_jobs


def parse_greenhouse_job(raw: dict) -> "JobLead | None":
    title = raw.get("title", "")
    if not _matches_title(title):
        return None
    company = raw.get("_company_slug", "").replace("-", " ").title()
    location_data = raw.get("location", {}) or {}
    location = location_data.get("name", "Unknown") if isinstance(location_data, dict) else str(location_data)
    url = raw.get("absolute_url", "")
    updated = (raw.get("updated_at", "") or "")[:10]
    return JobLead(
        title=title, company=company, url=url, location=location,
        posted_date=updated, description_snippet="",
        source="greenhouse", utility=0, risk=0, net_score=0,
        connection_proximity="unknown",
    )


# ── Lever Fetcher ─────────────────────────────────────────────────────────────

def fetch_lever_jobs(slugs: list[str] = LEVER_SLUGS) -> list[dict]:
    """Fetch jobs from Lever public API. No auth required."""
    raw_jobs = []
    client = httpx.Client(timeout=10)
    for slug in slugs:
        try:
            url = f"https://api.lever.co/v0/postings/{slug}"
            resp = client.get(url)
            if resp.status_code == 200:
                for job in resp.json():
                    job["_company_slug"] = slug
                    raw_jobs.append(job)
        except Exception as e:
            print(f"[Lead Gen] Lever error for '{slug}': {e}")
        time.sleep(0.3)
    client.close()
    print(f"[Lead Gen] Lever: {len(raw_jobs)} total raw jobs")
    return raw_jobs


def parse_lever_job(raw: dict) -> "JobLead | None":
    title = raw.get("text", "")
    if not _matches_title(title):
        return None
    company = raw.get("_company_slug", "").replace("-", " ").title()
    categories = raw.get("categories", {}) or {}
    location = categories.get("location", "Unknown") if isinstance(categories, dict) else "Unknown"
    url = raw.get("hostedUrl", raw.get("applyUrl", ""))
    created_ts = raw.get("createdAt", 0)
    if created_ts:
        posted = datetime.fromtimestamp(created_ts / 1000).strftime("%Y-%m-%d")
    else:
        posted = ""
    # Brief description from first list item
    lists = raw.get("lists", []) or []
    snippet = ""
    for lst in lists[:1]:
        content = lst.get("content", "")
        snippet = re.sub(r'<[^>]+>', '', content)[:200]
    return JobLead(
        title=title, company=company, url=url, location=location,
        posted_date=posted, description_snippet=snippet,
        source="lever", utility=0, risk=0, net_score=0,
        connection_proximity="unknown",
    )


# ── Direct Career Page Scraper ────────────────────────────────────────────────

def fetch_direct_career_pages(pages: dict = DIRECT_CAREER_PAGES) -> list[JobLead]:
    """
    Scrape direct career pages. Rate-limited to min 2s between requests.
    Returns only jobs matching TARGET_TITLE_PATTERNS.
    Gracefully skips companies where fetch fails or blocks.
    """
    from bs4 import BeautifulSoup
    leads = []
    client = httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
    for company, url in pages.items():
        try:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"[Lead Gen] {company}: HTTP {resp.status_code} — skipping")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            # Generic job title extraction — look for anchor text or heading text
            job_titles = set()
            for tag in soup.find_all(["a", "h2", "h3", "h4", "li"], string=True):
                text = tag.get_text(strip=True)
                if _matches_title(text):
                    href = tag.get("href", "") if tag.name == "a" else ""
                    if href and not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    if text not in job_titles:
                        job_titles.add(text)
                        leads.append(JobLead(
                            title=text, company=company, url=href or url,
                            location="See posting", posted_date="",
                            description_snippet="",
                            source="direct", utility=0, risk=0, net_score=0,
                            connection_proximity="unknown",
                        ))
            if job_titles:
                print(f"[Lead Gen] {company}: {len(job_titles)} relevant titles found")
        except Exception as e:
            print(f"[Lead Gen] {company}: Fetch error — {e}")
        time.sleep(2)  # Respect rate limits
    client.close()
    return leads


# ── Apify LinkedIn Jobs ───────────────────────────────────────────────────────

def fetch_apify_linkedin_jobs(api_key: str) -> list[JobLead]:
    """
    Use Apify LinkedIn Jobs Scraper. Requires APIFY_API_KEY.
    Polls for run completion (max 120s). Returns empty list if key missing or fails.
    """
    if not api_key:
        print("[Lead Gen] Apify: No API key — skipping LinkedIn scraping")
        return []

    # Build LinkedIn job search URLs (actor requires urls, not keyword strings)
    # Bias toward growth-stage companies (startup, series B/C) and Boston/hybrid.
    # Avoid generic big-company searches — operator background is differentiated
    # at companies where one executive can move the needle, not at FAANG/Tier-1 banks.
    from urllib.parse import urlencode
    search_params = [
        # Boston-area FinTech leadership
        {"keywords": "Chief Product Officer fintech payments", "location": "Boston, Massachusetts"},
        {"keywords": "Chief Technology Officer startup fintech", "location": "Boston, Massachusetts"},
        {"keywords": "VP Product embedded finance digital banking", "location": "Boston, Massachusetts"},
        # Growth-stage payments / embedded finance — remote/hybrid OK
        {"keywords": "CPO CTO startup payments embedded banking", "location": "United States"},
        {"keywords": "Head of Product payments fintech startup", "location": "United States"},
        # Digital identity — unique angle from SoyYo background
        {"keywords": "VP Product digital identity KYC fintech", "location": "United States"},
        {"keywords": "Chief Product Officer digital identity verification", "location": "United States"},
        # Agentic AI / AI-native FinTech — emerging target category
        {"keywords": "CPO CTO agentic AI financial services", "location": "United States"},
        # Credit union technology / CUSO enablers — active SMCU role is instant credibility
        {"keywords": "Chief Product Officer credit union fintech CUSO", "location": "United States"},
        {"keywords": "VP Product Head of Product credit union technology", "location": "United States"},
        # LATAM-origin companies expanding to US — East Coast / NYC / Miami / Boston
        {"keywords": "Chief Product Officer Latin America payments expansion", "location": "United States"},
        {"keywords": "VP General Manager Latin America fintech payments", "location": "United States"},
        {"keywords": "Head of Product US expansion neobank", "location": "New York"},
        {"keywords": "CPO CTO nubank dlocal mercadopago ebanx US", "location": "United States"},
    ]
    base = "https://www.linkedin.com/jobs/search/?"
    urls = [base + urlencode(p) for p in search_params]

    actor_id = "curious_coder~linkedin-jobs-scraper"
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
    headers = {"Authorization": f"Bearer {api_key}"}
    input_data = {
        "urls": urls,
        "maxItems": 50,
    }

    try:
        run_resp = httpx.post(
            run_url, json=input_data, headers=headers,
            params={"waitForFinish": 120}, timeout=150
        )
        run_resp.raise_for_status()
        data = run_resp.json()["data"]
        status = data.get("status", "")
        dataset_id = data.get("defaultDatasetId", "")
        print(f"[Lead Gen] Apify run status: {status}, dataset: {dataset_id}")

        if status not in ("SUCCEEDED", "READY"):
            # If not finished yet, poll briefly
            run_id = data.get("id", "")
            for _ in range(12):  # max 60s extra
                time.sleep(5)
                status_resp = httpx.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    headers=headers, timeout=15
                )
                status = status_resp.json()["data"]["status"]
                dataset_id = status_resp.json()["data"]["defaultDatasetId"]
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    print(f"[Lead Gen] Apify run failed with status: {status}")
                    return []

        # Retrieve dataset
        items_resp = httpx.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            headers=headers, params={"format": "json", "limit": 100}, timeout=30
        )
        items = items_resp.json() if items_resp.status_code == 200 else []

        leads = []
        for item in items:
            title = item.get("title", "")
            if not _matches_title(title):
                continue
            leads.append(JobLead(
                title=title,
                company=item.get("companyName", item.get("company", "")),
                url=item.get("url", item.get("link", "")),
                location=item.get("location", ""),
                posted_date=item.get("postedAt", "")[:10] if item.get("postedAt") else "",
                description_snippet=item.get("descriptionText", item.get("descriptionSnippet", ""))[:200],
                source="apify",
                utility=0, risk=0, net_score=0,
                connection_proximity="unknown",
            ))
        print(f"[Lead Gen] Apify: {len(leads)} relevant leads found")
        return leads
    except Exception as e:
        print(f"[Lead Gen] Apify error: {e}")
        return []


# ── Contact Proximity ─────────────────────────────────────────────────────────

def _normalize_company(name: str) -> str:
    """Lowercase, strip legal suffixes, trim whitespace for fuzzy matching."""
    name = name.lower().strip()
    for suffix in [" inc", " llc", " corp", " ltd", " limited", " co.", ", inc.", ", llc"]:
        name = name.replace(suffix, "")
    return name.strip()


def load_contacts(csv_path: Path) -> dict[str, str]:
    """
    Load LinkedIn contacts CSV export.
    Expected columns (LinkedIn standard): First Name, Last Name, Company, Position
    Returns dict: {normalized_company_name: "First Last (Position)"}
    Multiple contacts at same company: keeps most senior by heuristic.
    """
    if not csv_path or not csv_path.exists():
        return {}

    contacts: dict[str, list[str]] = {}
    SENIORITY_KEYWORDS = ["chief", "vp", "svp", "evp", "president", "partner",
                          "director", "head of", "managing", "founder", "cto", "cpo", "ceo"]

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Normalize headers
            headers = {k.strip().lower(): k for k in reader.fieldnames or []}
            for row in reader:
                norm = {k.strip().lower(): v.strip() for k, v in row.items()}
                company = norm.get("company", "")
                if not company:
                    continue
                company_key = _normalize_company(company)
                first = norm.get("first name", "")
                last = norm.get("last name", "")
                position = norm.get("position", "")
                full = f"{first} {last}".strip()
                entry = f"{full} ({position})" if position else full
                contacts.setdefault(company_key, []).append((position.lower(), entry))

        # Keep most senior contact per company
        result = {}
        for company_key, entries in contacts.items():
            # Sort by seniority keyword presence
            def seniority_rank(e):
                pos_lower = e[0]
                return sum(1 for kw in SENIORITY_KEYWORDS if kw in pos_lower)
            entries.sort(key=seniority_rank, reverse=True)
            result[company_key] = entries[0][1]

        print(f"[Lead Gen] Loaded {len(result)} companies from contacts CSV")
        return result
    except Exception as e:
        print(f"[Lead Gen] Error loading contacts CSV: {e}")
        return {}


def apply_connection_proximity(leads: list[JobLead], contacts: dict[str, str]) -> list[JobLead]:
    """Apply 1st-degree flags to leads where company matches contacts."""
    for lead in leads:
        company_key = _normalize_company(lead.company)
        # Also try partial matches for common company name variations
        matched = contacts.get(company_key)
        if not matched:
            for contact_co in contacts:
                if company_key in contact_co or contact_co in company_key:
                    matched = contacts[contact_co]
                    break
        if matched:
            lead.connection_proximity = "1st"
            lead.contact_name = matched
    return leads


# ── Claude Scoring ────────────────────────────────────────────────────────────

SCORING_PROMPT = """Score these executive job leads for a senior FinTech leader.

EXECUTIVE PROFILE:
{profile}

LEADS TO SCORE (JSON array):
{leads_json}

For each lead, assign:
- utility (1-10): title seniority + sector alignment to executive's expertise + location fit
- risk (1-10): signs role may be already filled, company instability, location mismatch, or role below seniority level

Return ONLY a valid JSON array of objects with exactly these fields:
[{{"utility": <int>, "risk": <int>}}, ...]

The array must have exactly {count} items in the same order. No explanation."""

FIT_ANALYSIS_PROMPT = """You are assessing how well an executive's background matches a specific job description.

EXECUTIVE PROFILE:
{profile}

JOB DESCRIPTION:
{jd_text}

ROLE: {title} at {company}

Analyze the fit and return ONLY valid JSON with exactly these fields:
{{
  "fit_score": <integer 0-100, where 100 = perfect match>,
  "fit_strengths": "<2-3 specific credentials from the profile that directly match JD requirements>",
  "fit_gaps": "<1-2 notable gaps or weaknesses vs this specific JD, or 'None identified' if strong match>",
  "utility": <integer 1-10, role seniority + sector alignment + location fit>,
  "risk": <integer 1-10, signs role may be filled, company instability, location mismatch, or below seniority>
}}

Be specific — reference actual JD language and actual profile credentials. No generic statements."""


def _fetch_jd_text(url: str) -> str:
    """Fetch and clean job description text from a URL. Returns empty string on failure."""
    if not url or not url.startswith("http"):
        return ""
    try:
        from bs4 import BeautifulSoup
        resp = httpx.get(url, timeout=12, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text[:4000]  # Cap at 4K — enough for JD content
    except Exception:
        return ""


def analyze_jd_fit(leads: list[JobLead]) -> list[JobLead]:
    """
    For each lead with a URL, fetch the full JD and run a CV-to-JD fit analysis
    via Claude Haiku. Sets fit_score, fit_strengths, fit_gaps, utility, risk on each lead.
    Leads without fetchable JDs fall back to the standard scoring prompt.
    """
    if not leads:
        return leads

    client = anthropic.Anthropic()
    needs_fallback = []

    for lead in leads:
        jd_text = _fetch_jd_text(lead.url)
        if not jd_text:
            needs_fallback.append(lead)
            continue

        prompt = FIT_ANALYSIS_PROMPT.format(
            profile=EXECUTIVE_PROFILE,
            jd_text=jd_text,
            title=lead.title,
            company=lead.company,
        )
        try:
            response = client.messages.create(
                model=MODEL_HAIKU,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            result = json.loads(raw)
            lead.fit_score = int(result.get("fit_score", 0))
            lead.fit_strengths = result.get("fit_strengths", "")
            lead.fit_gaps = result.get("fit_gaps", "")
            lead.utility = int(result.get("utility", 5))
            lead.risk = int(result.get("risk", 5))
            lead.net_score = compute_net_score(lead.utility, lead.risk)
        except Exception as e:
            print(f"[Lead Gen] JD fit analysis error for {lead.company}: {e}")
            needs_fallback.append(lead)
        time.sleep(0.5)  # Rate limit courtesy

    # Fallback: score leads where JD fetch failed using batch scoring
    if needs_fallback:
        print(f"[Lead Gen] Falling back to batch scoring for {len(needs_fallback)} leads without JD text")
        needs_fallback = score_leads(needs_fallback)

    return leads


def score_leads(leads: list[JobLead], batch_size: int = 5) -> list[JobLead]:
    """Score leads using Claude Haiku in batches of 5. Assigns utility, risk, net_score."""
    if not leads:
        return []

    client = anthropic.Anthropic()

    for i in range(0, len(leads), batch_size):
        batch = leads[i:i + batch_size]
        batch_data = [
            {"title": l.title, "company": l.company, "location": l.location,
             "snippet": l.description_snippet[:150]}
            for l in batch
        ]
        prompt = SCORING_PROMPT.format(
            profile=EXECUTIVE_PROFILE,
            leads_json=json.dumps(batch_data, indent=2),
            count=len(batch),
        )
        try:
            response = client.messages.create(
                model=MODEL_HAIKU,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            scores = json.loads(raw)
            if len(scores) != len(batch):
                scores = [{"utility": 5, "risk": 5}] * len(batch)
        except Exception as e:
            print(f"[Lead Gen] Scoring error (batch {i}): {e}")
            scores = [{"utility": 5, "risk": 5}] * len(batch)

        for lead, score in zip(batch, scores):
            lead.utility = int(score.get("utility", 5))
            lead.risk = int(score.get("risk", 5))
            lead.net_score = compute_net_score(lead.utility, lead.risk)
            # Boost score for 1st-degree connections
            if lead.connection_proximity == "1st":
                lead.net_score = round(lead.net_score + 1.0, 2)

    return leads


def _assign_tiers(leads: list[JobLead]) -> list[JobLead]:
    for lead in leads:
        if lead.net_score >= 7.0:
            lead.tier = "HOT"
        elif lead.net_score >= 5.0:
            lead.tier = "WARM"
        else:
            lead.tier = "WATCH"
    return leads


# ── Deduplication ─────────────────────────────────────────────────────────────

def dedupe_leads(leads: list[JobLead]) -> list[JobLead]:
    """Remove duplicates by (normalized title, normalized company)."""
    seen = set()
    unique = []
    for lead in leads:
        key = (_normalize_company(lead.title), _normalize_company(lead.company))
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


# ── Report Formatter ──────────────────────────────────────────────────────────

def format_report(leads: list[JobLead]) -> str:
    hot = [l for l in leads if l.tier == "HOT"]
    warm = [l for l in leads if l.tier == "WARM"]
    watch = [l for l in leads if l.tier == "WATCH"]

    def render_lead(l: JobLead) -> str:
        proximity = f" | **Connection**: {l.connection_proximity}" + (f" — {l.contact_name}" if l.contact_name else "") if l.connection_proximity != "unknown" else ""
        fit_line = f"- **Fit Score**: {l.fit_score}/100\n" if l.fit_score else ""
        strengths_line = f"- **Strengths**: {l.fit_strengths}\n" if l.fit_strengths else ""
        gaps_line = f"- **Gaps**: {l.fit_gaps}\n" if l.fit_gaps else ""
        return (
            f"\n### {l.title} — {l.company}\n"
            f"- **Location**: {l.location} | **Posted**: {l.posted_date or 'N/A'} | **Source**: {l.source}\n"
            f"- **Utility**: {l.utility}/10 | **Risk**: {l.risk}/10 | **Net Score**: {l.net_score}"
            + proximity + "\n"
            + fit_line + strengths_line + gaps_line
            + (f"- **Description**: {l.description_snippet}\n" if l.description_snippet else "")
            + f"- **URL**: {l.url or 'N/A'}\n"
            + "\n---"
        )

    lines = [
        "# Lead Generation Report",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        f"_Total leads: {len(leads)} | HOT: {len(hot)} | WARM: {len(warm)} | WATCH: {len(watch)}_",
        f"_Net Score = Utility − (Risk × 0.4). +1.0 bonus for 1st-degree connection. Fit Score = CV-to-JD match (0–100)._",
        "",
    ]

    if hot:
        lines += [f"## HOT — Apply Immediately (Net ≥ 7.0)", *[render_lead(l) for l in sorted(hot, key=lambda x: x.net_score, reverse=True)], ""]
    if warm:
        lines += [f"## WARM — Research + Warm Intro Needed (Net 5.0–6.9)", *[render_lead(l) for l in sorted(warm, key=lambda x: x.net_score, reverse=True)], ""]
    if watch:
        lines += [f"## WATCH — Monitor Only (Net < 5.0)", *[render_lead(l) for l in sorted(watch, key=lambda x: x.net_score, reverse=True)], ""]

    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run(
    contacts_csv: Path = None,
    apify_key: str = "",
    score: bool = True,
    save_cache: bool = True,
) -> str:
    """
    Main entry point for Module 3.

    Args:
        contacts_csv: Path to LinkedIn contacts CSV export (optional)
        apify_key: Apify API key for LinkedIn scraping (optional)
        score: Whether to call Claude Haiku for scoring
        save_cache: Persist results to data/

    Returns:
        Markdown report string.
    """
    print("[Lead Gen] Starting lead generation...")

    # 1. Fetch from all sources
    all_leads: list[JobLead] = []

    gh_raw = fetch_greenhouse_jobs()
    for raw in gh_raw:
        lead = parse_greenhouse_job(raw)
        if lead:
            all_leads.append(lead)

    lever_raw = fetch_lever_jobs()
    for raw in lever_raw:
        lead = parse_lever_job(raw)
        if lead:
            all_leads.append(lead)

    direct_leads = fetch_direct_career_pages()
    all_leads.extend(direct_leads)

    if apify_key:
        linkedin_leads = fetch_apify_linkedin_jobs(apify_key)
        all_leads.extend(linkedin_leads)

    # 2. Deduplicate
    all_leads = dedupe_leads(all_leads)
    print(f"[Lead Gen] {len(all_leads)} unique leads after dedup")

    # 3. Contact proximity
    if contacts_csv is None:
        contacts_csv = CONTACTS_CSV
    contacts = load_contacts(contacts_csv)
    all_leads = apply_connection_proximity(all_leads, contacts)

    # 4. Score
    if score:
        print(f"[Lead Gen] Analyzing JD fit for {len(all_leads)} leads via Claude Haiku...")
        all_leads = analyze_jd_fit(all_leads)
    else:
        for lead in all_leads:
            lead.utility = 5
            lead.risk = 5
            lead.net_score = compute_net_score(5, 5)

    # 5. Assign tiers and sort
    all_leads = _assign_tiers(all_leads)
    all_leads.sort(key=lambda l: l.net_score, reverse=True)

    # 6. Persist
    if save_cache:
        cache_path = DATA_DIR / "leads_pipeline.json"
        cache_path.write_text(
            json.dumps([asdict(l) for l in all_leads], indent=2, default=str),
            encoding="utf-8"
        )
        print(f"[Lead Gen] Cached to {cache_path}")

    # 7. Report
    report = format_report(all_leads)
    report_path = DATA_DIR / "leads_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[Lead Gen] Report saved to {report_path}")

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Lead Generation — discover executive job openings")
    parser.add_argument("--contacts", type=Path, default=None,
                        help="Path to LinkedIn contacts CSV export")
    parser.add_argument("--no-score", action="store_true",
                        help="Skip Claude scoring (faster, uniform scores)")
    args = parser.parse_args()

    apify_key = os.environ.get("APIFY_API_KEY", "")
    report = run(
        contacts_csv=args.contacts,
        apify_key=apify_key,
        score=not args.no_score,
    )
    print("\n" + "="*60)
    print(report)
