"""
Outreach Generator — template-based drafts and context assembly.
AI generation is handled by Claude via MCP tools; this module is data/logic only.
"""

from typing import Optional, List


# ── Outreach Context Assembly ─────────────────────────────────────────────────

TYPE_INSTRUCTIONS = {
    "cold": "Open with a genuine, specific connection point (MIT Sloan, FinTech community, Boston, mutual work). Do not fabricate shared history.",
    "event_met": "Reference the in-person meeting specifically — where, when, what you discussed.",
    "followup": "Acknowledge briefly that you reached out before, add new value, re-ask.",
    "linkedin_dm": (
        "This is a LinkedIn DIRECT MESSAGE, not an email. Keep it under 75 words. "
        "Casual, warm tone. End with 'Open to a quick call?'"
    ),
    "connection_request_a": (
        "LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total. "
        "Reference something specific about their work or company. Do NOT ask for a job. End warmly."
    ),
    "connection_request_b": (
        "LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total. "
        "Brief Dalton style, light ask for perspective. Do NOT ask for a job. End warmly."
    ),
}

DALTON_RULES = (
    "STRICT DALTON RULES:\n"
    "1. Body ≤75 words (300 chars max for connection requests)\n"
    "2. First-person, direct voice — no corporate speak\n"
    "3. At least half the words focus on the contact or their work, not Santiago\n"
    "4. One specific Santiago credential woven in naturally (SoyYo, Avianca, Uff Movil, MIT Sloan)\n"
    "5. Subject line: specific and curiosity-inducing — not 'Following up' or 'Job Opportunity'\n"
    "6. FORBIDDEN: 'hope this finds you', 'excited to', 'pick your brain', 'circle back',\n"
    "   'touch base', 'synergy', 'I am looking for opportunities', 'I would love to connect'\n"
    "7. No em dashes, en dashes, or hyphens anywhere in the text\n"
    "8. Do NOT include a signature block\n"
    "9. If connection degree is 1 or warmth is 'warm', reference that shared context naturally"
)


def build_outreach_context(
    company,
    contact=None,
    email_type: str = "cold",
    context: Optional[str] = None,
    hook: Optional[str] = None,
    ask: Optional[str] = None,
    prior_message: Optional[str] = None,
) -> dict:
    """
    Assemble outreach context dict for Claude to generate a Dalton 6-point message.
    No API calls — pure data assembly from DB objects.
    """
    contact_info = {}
    if contact:
        contact_info = {
            "name": contact.name,
            "title": contact.title or "unknown title",
            "connection_degree": contact.connection_degree or "unknown",
            "warmth": contact.warmth or "cold",
            "met_via": getattr(contact, "met_via", None),
            "relationship_notes": getattr(contact, "relationship_notes", None),
            "email": contact.email,
        }
    else:
        contact_info = {"name": None, "note": f"No specific contact at {company.name}"}

    is_connection_request = email_type in ("connection_request_a", "connection_request_b")
    is_linkedin_dm = email_type == "linkedin_dm"

    if is_connection_request:
        return_format = '{"subject": "", "body": "<connection note, ≤300 characters>", "word_count": <int>, "rationale": "<one sentence>"}'
    elif is_linkedin_dm:
        return_format = '{"subject": "", "body": "<LinkedIn DM, ≤75 words>", "word_count": <int>, "rationale": "<one sentence>"}'
    else:
        return_format = '{"subject": "<subject line>", "body": "<email body, ≤75 words>", "word_count": <int>, "rationale": "<one sentence: hook used and why>"}'

    return {
        "company": {
            "name": company.name,
            "intel_summary": getattr(company, "intel_summary", None),
            "stage": getattr(company, "stage", None),
        },
        "contact": contact_info,
        "email_type": email_type,
        "type_instruction": TYPE_INSTRUCTIONS.get(email_type, ""),
        "hook": hook,
        "ask": ask or "Ask for their perspective or advice on a specific topic — never ask for a job.",
        "context": context,
        "prior_message": prior_message,
        "dalton_rules": DALTON_RULES,
        "return_format": return_format,
    }


# ── Follow-up Email Templates (No API cost) ─────────────────────────────────

FOLLOW_UP_TEMPLATES = {
    "day_3": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nJust wanted to make sure my note didn't get buried. Would love to hear your perspective whenever you have a few minutes.\n\nSantiago",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nQuería asegurarme de que mi mensaje no se perdiera. Me encantaría escuchar tu perspectiva cuando tengas unos minutos.\n\nSantiago",
        },
    },
    "day_7": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nI don't mean to be a bother. If I don't hear back, I'll take that as a no and won't follow up again. I genuinely appreciated the chance to reach out.\n\nSantiago",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nNo quiero ser un inconveniente. Si no recibo respuesta, lo tomaré como un no y no volveré a escribir. Genuinamente aprecié la oportunidad de contactarte.\n\nSantiago",
        },
    },
    "harvest": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nCircling back one last time. If there's ever a moment to connect, I'd welcome it.\n\nSantiago",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nVuelvo a escribirte una última vez. Si en algún momento hay oportunidad de conversar, lo agradecería mucho.\n\nSantiago",
        },
    },
}


def draft_followup_from_template(stage: str, outreach_record: dict, language: str = "en") -> dict:
    """
    Generate follow-up email from template based on conversation stage.
    No API call — uses predefined templates for standard follow-ups.

    Args:
        stage: "day_3" | "day_7" | "harvest"
        outreach_record: Dict with company, contact_name, contact_role, sent_date, notes, etc.
        language: "en" or "es"

    Returns:
        {subject, body, stage, template_used: True}
    """
    if stage not in FOLLOW_UP_TEMPLATES:
        return {"error": f"Unknown stage: {stage}"}

    lang = language if language in ("en", "es") else "en"
    template = FOLLOW_UP_TEMPLATES[stage][lang]
    subject_template = template["subject"]
    body_template = template["body"]

    first_name = outreach_record.get("contact_name", "").split()[0] or "there"
    original_subject = outreach_record.get("generated_subject", "our conversation")
    brief_context = outreach_record.get("contact_role", "the role")

    from datetime import datetime, date
    sent_date_str = outreach_record.get("sent_date", "")
    try:
        sent_date = datetime.fromisoformat(sent_date_str).date()
        days_since = (date.today() - sent_date).days
    except (ValueError, TypeError):
        days_since = 0

    subject = subject_template.format(
        original_subject=original_subject,
        first_name=first_name,
    )
    body = body_template.format(
        first_name=first_name,
        brief_context=brief_context,
        days_since=f"{days_since} days" if days_since != 1 else "1 day",
    )

    return {
        "subject": subject,
        "body": body,
        "stage": stage,
        "template_used": True,
        "word_count": len(body.split()),
        "reasoning": f"Generated from {stage} template (no API call)",
    }


# ── Interview Prep Context Assembly ──────────────────────────────────────────

INTERVIEW_PREP_INSTRUCTIONS = """Generate a strategic company brief with exactly these 6 sections. Return valid JSON only.

RULES:
- Every sentence must be about the company, not about the reader.
- Never say "your background", "your experience", "you fit", or anything framing the reader.
- Write in plain English. Spell out jargon on first use.
- No em dashes. Use plain dashes or rewrite.
- Be specific and concrete. Avoid generic consulting language.
- Section 5 must accurately reflect the conversation history provided. If there is no history, say so plainly.
- Section 6 questions must be peer-level and show genuine strategic curiosity. Not interview prep questions. Do NOT ask about career advice, what they look for in candidates, or what they would do in your position.

{
  "sections": [
    {"title": "What is Actually Happening Right Now", "content": "2-3 paragraphs. Recent moves, funding, acquisitions, leadership changes."},
    {"title": "Their Biggest Strategic Challenges", "content": "Numbered list. 2-3 challenges, each in 2-3 sentences."},
    {"title": "Competitive Landscape", "content": "1-2 paragraphs. Who they compete against, how they are positioned."},
    {"title": "What They Likely Need at the Leadership Level", "content": "2-3 bullet points. Frame as company needs, not reader qualifications."},
    {"title": "Our History with This Company", "content": "Plain summary of prior contact. If none: No prior outreach on record."},
    {"title": "Questions Worth Asking", "content": "3-4 questions. Sharp, specific, peer-level."}
  ]
}"""


def build_interview_prep_context(
    company,
    contact_name: str = "",
    contact_title: str = "",
    role_title: str = "",
    intel_summary: str = "",
    org_notes: str = "",
    recent_news: str = "",
    open_roles: list = [],
    conversation_history: str = "",
) -> dict:
    """
    Assemble interview prep context dict for Claude to generate the 6-section brief.
    No API calls — pure data assembly.
    """
    return {
        "company_name": company.name,
        "contact_name": contact_name,
        "contact_title": contact_title,
        "role_title": role_title,
        "intel_summary": intel_summary or "Not available.",
        "org_notes": org_notes or "Not available.",
        "recent_news": recent_news or "Not available.",
        "open_roles": open_roles,
        "conversation_history": conversation_history or "No prior contact on record.",
        "generation_instructions": INTERVIEW_PREP_INSTRUCTIONS,
    }


# ── TIARA Prep (legacy CLI only) ─────────────────────────────────────────────

async def generate_tiara_prep(company, role_title: str = "") -> dict:
    """
    Generate TIARA informational meeting prep questions.
    Legacy CLI function — not wired to HTTP or MCP.
    """
    import anthropic

    def _get_profile() -> str:
        from skills.shared import EXECUTIVE_PROFILE
        return EXECUTIVE_PROFILE

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
