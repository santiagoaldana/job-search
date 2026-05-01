"""
Startup Discovery — weekly Claude-powered search for Series B/C targets.
Prioritizes Boston/Cambridge presence or remote-first culture.
Stores as AITargetSuggestion records for Santiago to approve/skip.
"""

import json
import re
import anthropic
from datetime import datetime

EXECUTIVE_PROFILE = None

DOMAINS = ["payments", "digital identity", "embedded banking", "agentic AI", "fraud prevention", "stablecoins", "crypto infrastructure"]


def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


async def run_discovery():
    """
    Ask Claude to suggest 5-10 Series B/C startups worth targeting.
    Saves new ones as AITargetSuggestion records.
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    prompt = f"""You are helping an executive find the right Series B/C startups for his job search.

CANDIDATE:
{profile}

TARGET DOMAINS: {', '.join(DOMAINS)}
LOCATION PREFERENCE: Boston/Cambridge MA area (in-person or hybrid) OR remote-first US companies

Task: Suggest 8 Series B or Series C startups that:
1. Operate in payments, digital identity, embedded banking, agentic AI, or fraud prevention
2. Are either headquartered/have offices in Boston/Cambridge OR are remote-first
3. Are likely hiring at C-suite or SVP level (growing fast enough to need senior leadership)
4. Would find Santiago's profile (MIT Sloan, exits at SoyYo/Uff Móvil, Avianca CDTO, LATAM expertise) compelling

For each company, explain WHY it's a good fit and WHY NOW is the right time to reach out.

Return ONLY valid JSON (no markdown fences):
[
  {{
    "name": "Company Name",
    "funding_stage": "series_b",
    "domain": "payments",
    "location_notes": "Boston-based / Remote-first",
    "reason": "2-sentence explanation of fit and timing"
  }}
]"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```.*$', '', raw, flags=re.DOTALL)
    # Extract JSON array even if there's preamble text
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        suggestions = json.loads(raw)
    except Exception:
        print(f"[startup_discovery] Failed to parse suggestions: {raw[:300]}")
        return

    from app.database import engine
    from sqlmodel import Session, select
    from app.models import AITargetSuggestion, Company

    saved = 0
    with Session(engine) as session:
        existing_companies = {
            c.name.lower() for c in session.exec(select(Company)).all()
        }
        existing_suggestions = {
            s.name.lower() for s in session.exec(select(AITargetSuggestion)).all()
        }

        for s in suggestions:
            name = s.get("name", "").strip()
            if not name:
                continue
            # Skip if already in DB or already suggested
            if name.lower() in existing_companies or name.lower() in existing_suggestions:
                continue

            suggestion = AITargetSuggestion(
                name=name,
                reason=s.get("reason", ""),
                funding_stage=s.get("funding_stage"),
                location_notes=s.get("location_notes"),
                domain=s.get("domain"),
                suggested_at=datetime.utcnow().isoformat(),
                reviewed=False,
                approved=False,
            )
            session.add(suggestion)
            saved += 1

        session.commit()

    print(f"[startup_discovery] {saved} new suggestions saved for review")
