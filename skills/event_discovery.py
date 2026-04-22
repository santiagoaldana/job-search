"""
Event Discovery Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search | Boston/Cambridge Hub

Discovers and scores networking events across:
- Eventbrite API
- Meetup API (via web scraping, API deprecated)
- MIT Sloan / Harvard / industry calendars (static targets)
- Manual entry support

Classification:
  HIGH_PROBABILITY  — Free or low-cost, local, high-density peer attendance
  STRATEGIC         — Paid/global forums, institutional credibility, keynote access
  WILDCARD          — Adjacent industries where leadership skills transfer

Risk/Utility scoring rubric:
  Utility  (1-10): Density of relevant decision-makers + topic alignment
  Risk     (1-10): Cost, time, likelihood of transactional vs. substantive conversations
  Net Score = Utility - (Risk * 0.4)   [utility-weighted, risk-discounted]
"""

import httpx
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Literal
import anthropic
from skills.shared import EXECUTIVE_PROFILE, compute_net_score, DATA_DIR, MODEL_OPUS

# ── Config ────────────────────────────────────────────────────────────────────

CACHE_PATH = DATA_DIR / "events_cache.json"

TARGET_KEYWORDS = [
    "fintech", "payments", "embedded finance", "banking", "BaaS",
    "stablecoin", "crypto", "blockchain", "open banking", "digital identity",
    "agentic AI", "agentic", "AI", "artificial intelligence", "machine learning",
    "insurtech", "regtech", "web3", "product leadership",
    "CTO", "CPO", "executive", "innovation", "venture", "startup",
    "credit union", "CUSO", "fraud", "digital transformation", "generative AI",
    "large language model", "LLM", "financial services", "capital markets",
]

LOCATION_TARGETS = ["Cambridge", "Boston", "Massachusetts", "MA", "New England"]

# Known high-value recurring events — manually curated
ANCHOR_EVENTS = [
    {
        "name": "MIT Imagination in Action 2026 — AI Workshop",
        "date": "2026-04-26",  # verify at imaginationinaction.co/2604mit/workshop
        "url": "https://imaginationinaction.co/2604mit/workshop",
        "location": "MIT, Cambridge MA",
        "cost": "See event page",
        "category": "STRATEGIC",
        "notes": (
            "MIT-hosted AI leadership workshop series. Strong overlap with agentic AI, "
            "enterprise AI deployment, and digital transformation themes. "
            "Likely audience: innovation executives, AI researchers, and corporate strategy leads. "
            "Santiago's CDTO Avianca + SoyYo AI/identity background is a strong fit. "
            "Entry point to MIT's AI ecosystem beyond Sloan."
        ),
        "utility": 8,
        "risk": 3,
    },
    {
        "name": "MIT Sloan CIO Symposium 2026",
        "date": "2026-05-20",  # approximate — verify at mitcio.com
        "url": "https://mitcio.com",
        "location": "MIT Sloan, Cambridge MA",
        "cost": "Included (Innovator Member)",
        "category": "STRATEGIC",
        "notes": (
            "Santiago is an Innovator Member. Highest-density CIO/CTO access in the MIT ecosystem. "
            "Prioritize pre-event dinner outreach to speakers 3 weeks in advance. "
            "Target: innovation leads at regional banks, payments infrastructure CTOs, and AI platform heads."
        ),
        "utility": 10,
        "risk": 2,
    },
    {
        "name": "NY Fintech Week 2026",
        "date": "2026-04-22",  # typically late April — verify at nyfintechweek.com
        "url": "https://nyfintechweek.com",
        "location": "New York, NY",
        "cost": "Paid (~$500–2,000 depending on tier)",
        "category": "STRATEGIC",
        "notes": (
            "High density of payment infrastructure, embedded finance founders, and BaaS operators. "
            "Warrants attendance ONLY if 3+ target companies are exhibiting or speaking. "
            "Risk: large expo floor dilutes 1:1 quality. Mitigate by booking side meetings in advance."
        ),
        "utility": 8,
        "risk": 5,
    },
    {
        "name": "Boston Fintech Week 2026",
        "date": "2026-10-01",  # typically October — verify at bostonfintechweek.com
        "url": "https://bostonfintechweek.com",
        "location": "Boston, MA",
        "cost": "Free / low-cost community tiers",
        "category": "HIGH_PROBABILITY",
        "notes": (
            "Local density with strong community of Series A–C founders and regional bank innovation leads. "
            "Best format for extended conversations vs. badge-scanning. "
            "Attend all side dinners — those are where actual decisions happen."
        ),
        "utility": 7,
        "risk": 2,
    },
    {
        "name": "Harvard Innovation Labs Demo Day",
        "date": "recurring",
        "url": "https://innovationlabs.harvard.edu",
        "location": "Cambridge, MA",
        "cost": "Free",
        "category": "HIGH_PROBABILITY",
        "notes": (
            "Cross-sector startup exposure. Relevant for Agentic AI and digital identity adjacencies. "
            "Target: venture partners scouting enterprise AI tools — they often need advisors with P&L track records."
        ),
        "utility": 6,
        "risk": 1,
    },
    {
        "name": "MIT Media Lab Events / Demo Days",
        "date": "recurring",
        "url": "https://www.media.mit.edu/events",
        "location": "MIT, Cambridge MA",
        "cost": "Free (MIT alumni access)",
        "category": "WILDCARD",
        "notes": (
            "WILDCARD — Adjacent to fintech but strong overlap with agentic AI, digital identity, "
            "and human-computer interaction research. "
            "Transferable angle: Santiago's digital identity + fraud prevention work maps directly "
            "to MIT's privacy/identity research agenda. Entry point to research commercialization roles."
        ),
        "utility": 6,
        "risk": 1,
    },
    {
        "name": "MassChallenge FinTech Demo Day",
        "date": "recurring",
        "url": "https://masschallenge.org",
        "location": "Boston, MA",
        "cost": "Free",
        "category": "HIGH_PROBABILITY",
        "notes": (
            "Boston's most active startup accelerator. Strong fintech cohort most years. "
            "Best ROI for meeting early-stage founders who need experienced operators — "
            "advisory board and fractional C-suite opportunities emerge here regularly."
        ),
        "utility": 7,
        "risk": 1,
    },
    {
        "name": "Nacha Smarter Faster Payments Conference",
        "date": "2026-04-27",  # typically late April
        "url": "https://www.nacha.org/payments-conference",
        "location": "Nashville, TN (typically)",
        "cost": "Paid (~$1,500–2,500)",
        "category": "STRATEGIC",
        "notes": (
            "The definitive ACH/payments infrastructure conference. "
            "High density of bank payments executives and fintech operators. "
            "ONLY attend if you have 5+ pre-booked 1:1s. Otherwise, high cost for diffuse ROI. "
            "Santiago's MVNO + PSP background resonates strongly here."
        ),
        "utility": 8,
        "risk": 6,
    },
    {
        "name": "Finovate Spring",
        "date": "2026-05-12",  # typically May — verify at finovate.com
        "url": "https://finance.knect365.com/finovatespring",
        "location": "San Francisco / hybrid",
        "cost": "Paid (~$1,800–3,500)",
        "category": "STRATEGIC",
        "notes": (
            "Demo-heavy format. Strong for meeting product and innovation leads at banks. "
            "Risk: dominated by vendor pitches. Santiago's angle is as a buyer/operator, "
            "not vendor — position accordingly to access the right conversations. "
            "Watch for LATAM-focused sessions — underserved but growing segment."
        ),
        "utility": 7,
        "risk": 6,
    },
    {
        "name": "HLTH Conference (Healthcare AI — Wildcard)",
        "date": "2026-10-18",  # typically October — verify at hlth.com
        "url": "https://www.hlth.com",
        "location": "Las Vegas, NV",
        "cost": "Paid (~$2,000–4,000)",
        "category": "WILDCARD",
        "notes": (
            "WILDCARD — Healthcare is the highest-spend adjacent sector for AI + digital identity + "
            "payments infrastructure. Patient identity, claims fraud, and embedded payments are "
            "exact analogues to Santiago's SoyYo digital identity work. "
            "Healthcare AI roles command 20–40% higher compensation than equivalent fintech roles. "
            "Risk: deep domain knowledge gap. Mitigation: lead with fraud/identity angle, not healthcare."
        ),
        "utility": 6,
        "risk": 7,
    },
]

# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class Event:
    name: str
    date: str
    url: str
    location: str
    cost: str
    category: Literal["HIGH_PROBABILITY", "STRATEGIC", "WILDCARD", "SKIP"]
    notes: str
    utility: int   # 1-10
    risk: int      # 1-10
    source: str = "manual"
    net_score: float = field(default=0.0, init=False)

    def __post_init__(self):
        self.net_score = compute_net_score(self.utility, self.risk)


# ── Eventbrite Fetcher ────────────────────────────────────────────────────────

def fetch_eventbrite_events(api_token: str, days_ahead: int = 90) -> list[dict]:
    """
    Fetch events from Eventbrite API filtered by location and keywords.
    Requires EVENTBRITE_API_TOKEN env var.
    Docs: https://www.eventbrite.com/platform/api
    """
    if not api_token:
        print("[EventBrite] No API token provided — skipping live fetch.")
        print("[EventBrite] Set EVENTBRITE_API_TOKEN env var to enable live discovery.")
        return []

    base_url = "https://www.eventbriteapi.com/v3/events/search/"
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []

    search_terms = ["fintech boston", "payments boston", "AI banking boston", "embedded finance"]
    for keyword in search_terms:
        params = {
            "q": keyword,
            "location.address": "Boston, MA",
            "location.within": "50mi",
            "start_date.range_end": end_date,
            "expand": "venue,ticket_availability",
            "token": api_token,
        }
        try:
            resp = httpx.get(base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("events", []))
            print(f"[EventBrite] '{keyword}': {len(data.get('events', []))} results")
        except httpx.HTTPStatusError as e:
            print(f"[EventBrite] HTTP error for '{keyword}': {e.response.status_code}")
        except Exception as e:
            print(f"[EventBrite] Error fetching '{keyword}': {e}")

    # Deduplicate by event ID
    seen = set()
    unique = []
    for e in results:
        eid = e.get("id")
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(e)
    return unique


def parse_eventbrite_event(raw: dict) -> "Event | None":
    """Convert raw Eventbrite API response to scored Event. Returns None if not relevant."""
    name = raw.get("name", {}).get("text", "")
    desc = raw.get("description", {}).get("text", "") or ""
    url = raw.get("url", "")
    start = raw.get("start", {}).get("local", "")[:10]
    venue = raw.get("venue", {}) or {}
    location = venue.get("address", {}).get("localized_address_display", "Unknown")
    is_free = raw.get("is_free", False)
    cost = "Free" if is_free else "Paid (check site)"

    combined_text = (name + " " + desc).lower()
    keyword_hits = sum(1 for kw in TARGET_KEYWORDS if kw.lower() in combined_text)
    is_local = any(
        loc.lower() in combined_text or loc.lower() in location.lower()
        for loc in LOCATION_TARGETS
    )

    if keyword_hits == 0:
        return None

    utility = min(10, 3 + keyword_hits + (2 if is_local else 0))
    risk = 2 if is_free else 6

    if is_free and is_local and keyword_hits >= 2:
        category = "HIGH_PROBABILITY"
    elif keyword_hits >= 3:
        category = "STRATEGIC"
    else:
        return None  # Not enough signal

    return Event(
        name=name,
        date=start,
        url=url,
        location=location,
        cost=cost,
        category=category,
        notes=f"Auto-discovered via Eventbrite. {keyword_hits} keyword matches. Local: {is_local}.",
        utility=utility,
        risk=risk,
        source="eventbrite",
    )


# ── Claude Enrichment ─────────────────────────────────────────────────────────

def enrich_events_with_claude(events: list[Event]) -> list[dict]:
    """
    Use Claude to generate a tactical networking brief for each event.
    """
    client = anthropic.Anthropic()
    enriched = []

    for i, event in enumerate(events):
        print(f"[Claude] Enriching event {i+1}/{len(events)}: {event.name}")
        prompt = f"""You are a no-nonsense strategic networking advisor for a senior executive in job search mode.

EXECUTIVE PROFILE:
{EXECUTIVE_PROFILE}

EVENT TO ANALYZE:
Name: {event.name}
Date: {event.date}
Location: {event.location}
Cost: {event.cost}
Category: {event.category}
Context: {event.notes}
Utility: {event.utility}/10 | Risk: {event.risk}/10 | Net Score: {event.net_score}

Write a tactical brief under 160 words covering exactly these four points:
1. TARGET: Who to seek out (describe role types, seniority, not company names)
2. OPENER: One non-generic conversation starter Santiago should use — value-proposition based, references a specific credential or insight, not "I'm looking for opportunities"
3. AVOID: One specific behavior or type of conversation that kills credibility at this event
4. WILDCARD: One non-obvious angle or unexpected type of person worth meeting here

No bullet-point padding. No "great opportunity" language. Be direct and specific."""

        try:
            response = client.messages.create(
                model=MODEL_OPUS,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            brief = response.content[0].text.strip()
        except Exception as e:
            brief = f"[Enrichment unavailable: {e}]"

        enriched_event = asdict(event)
        enriched_event["tactical_brief"] = brief
        enriched.append(enriched_event)

    return enriched


# ── Report Formatter ──────────────────────────────────────────────────────────

def format_report(events: list[dict]) -> str:
    strategic  = sorted([e for e in events if e["category"] == "STRATEGIC"],  key=lambda x: x["net_score"], reverse=True)
    high_prob  = sorted([e for e in events if e["category"] == "HIGH_PROBABILITY"], key=lambda x: x["net_score"], reverse=True)
    wildcard   = sorted([e for e in events if e["category"] == "WILDCARD"],   key=lambda x: x["net_score"], reverse=True)

    def render(e: dict) -> str:
        return (
            f"\n### {e['name']}\n"
            f"- **Date**: {e['date']}\n"
            f"- **Location**: {e['location']}\n"
            f"- **Cost**: {e['cost']}\n"
            f"- **Utility**: {e['utility']}/10 | **Risk**: {e['risk']}/10 | **Net Score**: {e['net_score']}\n"
            f"- **URL**: {e['url']}\n"
            f"- **Context**: {e['notes']}\n"
            + (f"\n**Tactical Brief**:\n{e['tactical_brief']}\n" if e.get('tactical_brief') else "")
            + "\n---"
        )

    sections = [
        f"# Event Discovery Report",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ",
        f"_Scope: Boston/Cambridge hub + MIT ecosystem + Global Strategic forums_",
        f"_Events scored: Utility − (Risk × 0.4) = Net Score_",
        "",
    ]

    if strategic:
        sections += ["## STRATEGIC — Paid/Global (High Institutional Value)", *[render(e) for e in strategic], ""]
    if high_prob:
        sections += ["## HIGH PROBABILITY — Free/Local (High Conversion Rate)", *[render(e) for e in high_prob], ""]
    if wildcard:
        sections += ["## WILDCARD — Adjacent Industries (Transferable Leadership)", *[render(e) for e in wildcard], ""]

    return "\n".join(sections)


# ── Luma Fetcher ─────────────────────────────────────────────────────────────

# Luma community slugs to monitor — these are public pages with event listings
LUMA_COMMUNITIES = [
    "bostonai",
    "mit-ai",
    "harvard-innovation",
    "boston-fintech",
    "new-england-tech",
]

# Luma keyword search terms (used against the public discover API)
LUMA_SEARCH_TERMS = [
    "AI Boston",
    "fintech Boston",
    "payments Boston",
    "AI MIT",
    "innovation Cambridge",
]

def fetch_luma_events(days_ahead: int = 90) -> list[Event]:
    """
    Fetch upcoming events from Luma city pages by parsing embedded __NEXT_DATA__ JSON.
    No API key required. Covers Boston and Cambridge.

    Returns scored Event objects. Gracefully returns [] on any failure.
    """
    import json as _json
    from datetime import timezone

    results: list[Event] = []
    seen_urls: set[str] = set()
    cutoff = datetime.now(tz=timezone.utc) + timedelta(days=days_ahead)

    # Luma city/hub pages to scrape
    luma_pages = [
        "https://luma.com/boston",
        "https://luma.com/cambridge",
    ]

    client = httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})

    for page_url in luma_pages:
        try:
            resp = client.get(page_url)
            if resp.status_code != 200:
                print(f"[Luma] {page_url}: HTTP {resp.status_code}")
                continue

            # Extract embedded Next.js page data
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                resp.text, re.DOTALL
            )
            if not match:
                print(f"[Luma] {page_url}: No __NEXT_DATA__ found")
                continue

            page_data = _json.loads(match.group(1))
            data = (page_data.get("props", {})
                             .get("pageProps", {})
                             .get("initialData", {})
                             .get("data", {}))

            raw_events = data.get("events", []) + data.get("featured_events", [])

            for raw in raw_events:
                ev = raw.get("event", raw)

                # Build URL from slug
                slug = ev.get("url", ev.get("slug", ""))
                url = f"https://lu.ma/{slug}" if slug and not slug.startswith("http") else slug
                if not url or url in seen_urls:
                    continue

                name = ev.get("name", "")
                if not name:
                    continue

                # Date — filter by cutoff
                start_at = ev.get("start_at", "")
                date_str = start_at[:10] if start_at else ""
                if start_at:
                    try:
                        ev_dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                        if ev_dt > cutoff:
                            continue
                    except ValueError:
                        pass

                # Location
                geo = ev.get("geo_address_info") or {}
                location = (geo.get("city_state") or
                            geo.get("address") or
                            ev.get("location_type", "Boston area"))

                # Cost
                ticket_info = ev.get("ticket_info") or {}
                is_free = ticket_info.get("is_free", True)
                cost = "Free" if is_free else "Paid (check lu.ma)"

                # Relevance scoring
                description = ev.get("description", "") or ""
                combined = (name + " " + description).lower()
                keyword_hits = sum(1 for kw in TARGET_KEYWORDS if kw.lower() in combined)
                is_local = any(loc.lower() in location.lower() for loc in LOCATION_TARGETS)

                # Require at least 1 keyword hit regardless of location.
                # Local geo alone is not enough — avoids yoga/art/community noise.
                if keyword_hits == 0:
                    continue

                utility = min(10, 4 + keyword_hits + (2 if is_local else 0))
                risk = 1 if is_free else 4

                category: Literal["HIGH_PROBABILITY", "STRATEGIC", "WILDCARD", "SKIP"] = (
                    "HIGH_PROBABILITY" if (is_free and is_local and keyword_hits >= 1) else
                    "STRATEGIC" if keyword_hits >= 2 else
                    "WILDCARD"
                )

                seen_urls.add(url)
                results.append(Event(
                    name=name,
                    date=date_str,
                    url=url,
                    location=location,
                    cost=cost,
                    category=category,
                    notes=f"Auto-discovered via Luma ({page_url.split('/')[-1]}). "
                          f"{keyword_hits} keyword matches. {description[:200]}",
                    utility=utility,
                    risk=risk,
                    source="luma",
                ))

            print(f"[Luma] {page_url.split('/')[-1]}: {len(results)} relevant events so far")

        except Exception as e:
            print(f"[Luma] Error fetching {page_url}: {e}")

    client.close()
    print(f"[Luma] Total: {len(results)} events found")
    return results


# ── Manual URL Intake ─────────────────────────────────────────────────────────

def add_event_from_url(url: str) -> Event:
    """
    Fetch an event page from a URL, extract key details, score it,
    and save it to the events cache alongside existing events.

    Works without Claude API — uses httpx + BeautifulSoup to extract text,
    then applies keyword scoring heuristics. If Claude is available,
    also generates a tactical brief.

    Returns the scored Event object.
    """
    from bs4 import BeautifulSoup

    print(f"[Event Discovery] Fetching: {url}")
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        page_text = soup.get_text(separator=" ", strip=True)
        page_text = " ".join(page_text.split())[:4000]
    except Exception as e:
        raise RuntimeError(f"Failed to fetch URL: {e}")

    # Extract title
    title_tag = soup.find("title")
    name = title_tag.get_text(strip=True) if title_tag else url

    # Extract date hints (simple regex — catches formats like April 9, 2026 / 2026-04-09)
    date_patterns = [
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}[–\-]?\d{0,2},?\s+\d{4}',
        r'\d{4}-\d{2}-\d{2}',
    ]
    date_found = ""
    for pat in date_patterns:
        m = re.search(pat, page_text)
        if m:
            date_found = m.group(0)
            break

    # Location hints
    location_found = "See event page"
    for loc_hint in ["Boston", "Cambridge", "New York", "San Francisco", "Chicago",
                     "London", "Davos", "Nashville", "Las Vegas", "MIT", "Harvard"]:
        if loc_hint.lower() in page_text.lower():
            location_found = loc_hint
            break

    # Cost hints
    cost_found = "See event page"
    if any(w in page_text.lower() for w in ["free", "no cost", "complimentary"]):
        cost_found = "Free"
    elif any(w in page_text.lower() for w in ["register", "ticket", "pricing", "$", "fee"]):
        cost_found = "Paid (check site)"

    # Keyword scoring
    keyword_hits = sum(1 for kw in TARGET_KEYWORDS if kw.lower() in page_text.lower())
    is_local = any(loc.lower() in page_text.lower() for loc in LOCATION_TARGETS)
    is_free = cost_found == "Free"

    utility = min(10, 4 + keyword_hits + (2 if is_local else 0))
    risk = 2 if is_free else 5

    if is_free and is_local:
        category = "HIGH_PROBABILITY"
    elif keyword_hits >= 2:
        category = "STRATEGIC"
    else:
        category = "WILDCARD"

    # Build summary from page text
    notes = f"Manually added from URL. {keyword_hits} keyword matches. " + page_text[:300] + "..."

    event = Event(
        name=name,
        date=date_found or "See event page",
        url=url,
        location=location_found,
        cost=cost_found,
        category=category,
        notes=notes,
        utility=utility,
        risk=risk,
        source="manual_url",
    )

    # Merge into existing cache
    existing: list[dict] = []
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
        except Exception:
            existing = []

    # Dedupe by URL
    existing = [e for e in existing if e.get("url") != url]
    existing.append(asdict(event))

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(existing, indent=2, default=str))

    # Regenerate report
    report = format_report(existing)
    report_path = DATA_DIR / "events_report.md"
    report_path.write_text(report)

    print(f"[Event Discovery] Added: {name}")
    print(f"  Date: {event.date} | Location: {event.location} | Cost: {event.cost}")
    print(f"  Category: {event.category} | Net Score: {event.net_score}")
    print(f"[Event Discovery] Report updated: {report_path}")

    return event


# ── Main ──────────────────────────────────────────────────────────────────────

def run(
    eventbrite_token: str = "",
    enrich: bool = True,
    save_cache: bool = True,
) -> str:
    """
    Main entry point for the Event Discovery module.

    Args:
        eventbrite_token: Eventbrite API token for live discovery (optional)
        enrich: Call Claude for tactical briefs (uses API credits)
        save_cache: Persist results to data/events_cache.json
    """
    print("[Event Discovery] Initializing...")

    # 1. Seed with curated anchor events
    events: list[Event] = [Event(**e) for e in ANCHOR_EVENTS]
    print(f"[Event Discovery] Loaded {len(events)} anchor events")

    # 2. Luma fetch (always runs — no API key needed)
    print("[Event Discovery] Fetching Luma events...")
    luma_events = fetch_luma_events()
    events.extend(luma_events)

    # 3. Live Eventbrite fetch (optional)
    if eventbrite_token:
        print("[Event Discovery] Fetching live Eventbrite events...")
        raw_eb = fetch_eventbrite_events(eventbrite_token)
        before = len(events)
        for raw in raw_eb:
            parsed = parse_eventbrite_event(raw)
            if parsed:
                events.append(parsed)
        print(f"[Event Discovery] Added {len(events) - before} events from Eventbrite")

    # Dedupe by URL across all sources
    seen_urls: set[str] = set()
    unique_events: list[Event] = []
    for e in events:
        if e.url not in seen_urls:
            seen_urls.add(e.url)
            unique_events.append(e)
    events = unique_events

    print(f"[Event Discovery] Total events: {len(events)}")

    # 4. Claude enrichment
    if enrich:
        print("[Event Discovery] Generating tactical briefs via Claude...")
        enriched = enrich_events_with_claude(events)
    else:
        enriched = [asdict(e) for e in events]
        print("[Event Discovery] Skipping Claude enrichment (--no-enrich flag set)")

    # 5. Persist
    if save_cache:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(enriched, f, indent=2, default=str)
        print(f"[Event Discovery] Cached to {CACHE_PATH}")

    # 6. Write report
    report = format_report(enriched)
    report_path = Path(__file__).parent.parent / "data" / "events_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"[Event Discovery] Report written to {report_path}")

    return report


if __name__ == "__main__":
    import os
    token = os.environ.get("EVENTBRITE_API_TOKEN", "")
    enrich_flag = "--no-enrich" not in sys.argv
    report = run(eventbrite_token=token, enrich=enrich_flag)
    print("\n" + "="*60)
    print(report)
