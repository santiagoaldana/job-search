"""
Fit Scoring Engine — Claude Haiku scores each lead 0-100 against Santiago's profile.
Also determines location_compatible flag.
"""

import json
import os
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import anthropic

EXECUTIVE_PROFILE = None  # lazy-loaded

ACCEPTED_LOCATIONS = {
    "cambridge", "boston", "remote", "hybrid", "nationwide",
    "us remote", "greater boston", "ma", "massachusetts",
    "new england", "flexible",
}


def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


EXCLUDED_TITLE_KEYWORDS = [
    "engineer", "developer", "architect", "data scientist",
    "analyst", "programmer", "devops", "sre", "qa tester",
    "tester", "scientist", "data engineer",
]

# Titles that contain excluded keywords but are actually exec/leadership roles
EXCLUDED_TITLE_EXEMPTIONS = [
    "chief", "vp", "svp", "evp", "director", "head of", "principal",
    "solutions architect",  # solutions architects are often strategic
]


TITLE_POSITIVE_KEYWORDS = [
    "chief", "cxo", "coo", "cto", "cpo", "ceo", "president",
    "vp", "svp", "evp", "head of", "director", "managing director",
    "general manager", "payments", "fintech", "embedded", "identity",
    "agentic", "fraud", "banking", "digital", "growth",
]

DESCRIPTION_POSITIVE_KEYWORDS = [
    "payments", "fintech", "fin-tech", "embedded banking", "digital identity",
    "fraud", "agentic", "latam", "latin america", "banking", "financial services",
    "series b", "series c", "growth stage", "scale", "expansion",
    "c-suite", "executive", "leadership", "strategy", "p&l",
]


def rule_score_lead(lead) -> dict:
    """
    Free rule-based fit scorer — no API call. Replaces Claude Haiku for auto-scoring.
    Returns same dict shape as score_lead() but with empty strengths/gaps lists.
    """
    title = (lead.title or "").lower()
    location = (lead.location or "").lower()
    description = (lead.description or "").lower()

    # Base score from title seniority/relevance
    title_hits = sum(1 for kw in TITLE_POSITIVE_KEYWORDS if kw in title)
    base_score = min(40 + title_hits * 8, 75)

    # Boost from description keyword density
    desc_hits = sum(1 for kw in DESCRIPTION_POSITIVE_KEYWORDS if kw in description)
    desc_boost = min(desc_hits * 3, 20)

    fit_score = float(base_score + desc_boost)
    fit_score = _apply_role_type_penalty(lead.title or "", fit_score)
    location_compatible = _is_location_compatible(location, lead.title or "", fit_score)

    return {
        "fit_score": round(fit_score, 1),
        "fit_strengths": [],
        "fit_gaps": [],
        "location_compatible": location_compatible,
        "reasoning": "rule-based score — click 'Deep Score' for AI analysis",
    }


def _apply_role_type_penalty(title: str, fit_score: float) -> float:
    title_lower = title.lower()
    if any(exempt in title_lower for exempt in EXCLUDED_TITLE_EXEMPTIONS):
        return fit_score
    if any(kw in title_lower for kw in EXCLUDED_TITLE_KEYWORDS):
        return min(fit_score, 40.0)
    return fit_score


def _is_location_compatible(location: str, title: str, fit_score: float) -> bool:
    """Cambridge/Boston/Remote = True. Onsite-only elsewhere = False unless SVP+ with high fit."""
    if not location:
        return True  # unknown = assume compatible
    loc_lower = location.lower()
    if any(accepted in loc_lower for accepted in ACCEPTED_LOCATIONS):
        return True
    # SVP+ role with very high fit might be worth pursuing even if location mismatch
    is_senior = any(t in title.lower() for t in ["svp", "evp", "cxo", "coo", "cto", "cpo",
                                                   "ceo", "president", "chief"])
    if is_senior and fit_score >= 80:
        return True
    return False


async def score_lead(lead) -> dict:
    """
    Score a single Lead against Santiago's profile.
    Returns dict with fit_score, fit_strengths, fit_gaps, location_compatible.
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    description = lead.description or ""
    title = lead.title or ""
    location = lead.location or ""

    prompt = f"""You are an executive recruiter evaluating candidate fit.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
Title: {title}
Location: {location}
Description: {description[:3000]}

Rate this candidate's fit for this role on a scale of 0-100, where:
- 90-100: Near-perfect match, strong competitive advantage
- 70-89: Strong fit, clear value proposition
- 50-69: Moderate fit, some gaps but transferable strengths
- 30-49: Weak fit, significant gaps
- 0-29: Poor fit

Return ONLY valid JSON (no markdown fences):
{{
  "fit_score": <integer 0-100>,
  "fit_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "fit_gaps": ["<gap 1>", "<gap 2>", "<gap 3>"],
  "reasoning": "<one sentence summary>"
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    import re
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    try:
        data = json.loads(raw)
    except Exception:
        data = {"fit_score": 50, "fit_strengths": [], "fit_gaps": [], "reasoning": "parse error"}

    fit_score = float(data.get("fit_score", 50))
    fit_score = _apply_role_type_penalty(title, fit_score)
    location_compatible = _is_location_compatible(location, title, fit_score)

    return {
        "fit_score": fit_score,
        "fit_strengths": data.get("fit_strengths", []),
        "fit_gaps": data.get("fit_gaps", []),
        "location_compatible": location_compatible,
        "reasoning": data.get("reasoning", ""),
    }


async def score_leads_batch(leads: list) -> list:
    """Score multiple leads. Returns list of result dicts in same order."""
    results = []
    for lead in leads:
        try:
            result = await score_lead(lead)
        except Exception as e:
            result = {
                "fit_score": None,
                "fit_strengths": [],
                "fit_gaps": [],
                "location_compatible": True,
                "reasoning": f"error: {e}",
            }
        results.append(result)
    return results
