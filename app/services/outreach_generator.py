"""
Outreach Generator — 6-point email generation (Dalton method) via Claude Opus.
Migrated and adapted from skills/network_pathfinder.py.
"""

import anthropic
from typing import Optional

EXECUTIVE_PROFILE = None


def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


async def generate_6point_email(
    company,
    contact=None,
    context: Optional[str] = None,
    hook: Optional[str] = None,
    ask: Optional[str] = None,
    email_type: str = "cold",
) -> dict:
    """
    Generate a 6-point ≤75-word outreach email (Dalton rules).
    Returns: {subject, body, word_count}
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    contact_info = ""
    if contact:
        contact_info = (
            f"Contact: {contact.name}, {contact.title or 'unknown title'} at {company.name}\n"
            f"Connection degree: {contact.connection_degree or 'unknown'}\n"
            f"Email: {contact.email or 'not known'}\n"
        )
    else:
        contact_info = f"Target company: {company.name} (no specific contact identified)\n"

    type_instruction = {
        "cold": "This is a cold outreach — open with a genuine connection point (MIT Sloan, FinTech community, Boston, mutual work).",
        "event_met": f"They MET IN PERSON at an event. Open by referencing that meeting specifically. Context: {context}",
        "followup": "This is a follow-up to a previous email with no reply. Acknowledge briefly, add new value, re-ask.",
    }.get(email_type, "")

    hook_instruction = f"\nLEAD WITH THIS SPECIFIC HOOK: {hook}" if hook else ""
    ask_instruction = f"\nTHE ASK: {ask}" if ask else "Ask for their perspective or advice on a specific topic — never ask for a job."

    prompt = f"""You are writing a networking outreach email for an executive job search.

SENDER PROFILE:
{profile}

{contact_info}
EMAIL TYPE: {type_instruction}
{hook_instruction}
{ask_instruction}
Additional context: {context or 'None provided'}

STRICT DALTON RULES:
1. Body ≤75 words — hard limit, count every word
2. First-person, direct voice — no corporate speak
3. At least half the words focus on the contact or their work, not Santiago
4. One specific Santiago credential woven in naturally (SoyYo, Avianca, Uff Móvil, MIT Sloan)
5. Subject line: specific and curiosity-inducing — not "Following up" or "Job Opportunity"
6. FORBIDDEN: "hope this finds you", "excited to", "pick your brain", "circle back",
   "touch base", "synergy", "I'm looking for opportunities", "I'd love to connect"

Return JSON (no markdown):
{{
  "subject": "<subject line>",
  "body": "<email body, ≤75 words>",
  "word_count": <integer>,
  "rationale": "<one sentence: hook used and why>"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    import json, re
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    try:
        data = json.loads(raw)
    except Exception:
        data = {
            "subject": f"Question about {company.name}",
            "body": raw[:300],
            "word_count": len(raw.split()),
            "rationale": "parse error",
        }

    return data


async def generate_tiara_prep(company, role_title: str = "") -> dict:
    """
    Generate TIARA informational meeting prep questions.
    Returns dict with sections: small_talk, trends, insights, advice, resources, assignments, closing
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    prompt = f"""Generate TIARA informational meeting prep for Santiago Aldana meeting someone at {company.name}.
Role being discussed: {role_title or 'executive/leadership role'}

CANDIDATE PROFILE:
{profile}

TIARA framework:
- T: Trends (macro forces affecting the company/industry)
- I: Insights (things only insiders would know)
- A: Advice (what would they do in Santiago's position)
- R: Resources (other people to talk to)
- A: Assignments (follow-ups to demonstrate interest)

Generate 2 questions per category plus:
- 2 warm-up small talk openers
- Closing script (how to end gracefully and follow up)

Return JSON:
{{
  "small_talk": ["q1", "q2"],
  "trends": ["q1", "q2"],
  "insights": ["q1", "q2"],
  "advice": ["q1"],
  "resources": ["q1", "q2"],
  "assignments": ["q1"],
  "closing": "<closing script 2-3 sentences>"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    import json, re
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    try:
        return json.loads(raw)
    except Exception:
        return {"error": "Failed to parse TIARA prep", "raw": raw[:500]}
