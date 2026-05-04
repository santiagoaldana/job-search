"""
Outreach Generator — 6-point email generation (Dalton method) via Claude Opus.
Migrated and adapted from skills/network_pathfinder.py.
"""

import anthropic
from typing import Optional, List

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
        degree = contact.connection_degree or "unknown"
        warmth = contact.warmth or "cold"
        met_via = getattr(contact, 'met_via', None)
        rel_notes = getattr(contact, 'relationship_notes', None)
        contact_info = (
            f"Contact: {contact.name}, {contact.title or 'unknown title'} at {company.name}\n"
            f"Connection degree: {degree} ({'direct LinkedIn connection' if degree == 1 else '2nd degree' if degree == 2 else 'no direct connection'})\n"
            f"Warmth: {warmth}\n"
        )
        if met_via:
            contact_info += f"How we met / intro context: {met_via}\n"
        if rel_notes:
            contact_info += f"Relationship notes: {rel_notes}\n"
        if contact.email:
            contact_info += f"Email: {contact.email}\n"
    else:
        contact_info = f"Target company: {company.name} (no specific contact identified)\n"

    type_instruction = {
        "cold": "This is a cold outreach — open with a genuine connection point (MIT Sloan, FinTech community, Boston, mutual work).",
        "event_met": f"They MET IN PERSON at an event. Open by referencing that meeting specifically. Context: {context}",
        "followup": "This is a follow-up to a previous email with no reply. Acknowledge briefly, add new value, re-ask.",
        "linkedin_dm": (
            "This is a LinkedIn DIRECT MESSAGE, not an email. Keep it under 75 words. "
            "Casual, warm tone. If prior email context is available, briefly reference it "
            "('Sent you a note last week — wanted to try here too'). End with 'Open to a quick call?'"
        ),
        "connection_request_a": (
            "This is a LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total (not words). "
            "Variant A — 'shared context' style: reference something specific about their work or company. "
            "Do NOT ask for a job. End warmly."
        ),
        "connection_request_b": (
            "This is a LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total (not words). "
            "Variant B — Dalton-style: brief, mostly about them, can include a light ask for their perspective. "
            "Do NOT ask for a job. End warmly."
        ),
    }.get(email_type, "")

    hook_instruction = f"\nLEAD WITH THIS SPECIFIC HOOK: {hook}" if hook else ""
    ask_instruction = f"\nTHE ASK: {ask}" if ask else "Ask for their perspective or advice on a specific topic — never ask for a job."

    is_connection_request = email_type in ("connection_request_a", "connection_request_b")
    is_linkedin_dm = email_type == "linkedin_dm"

    if is_connection_request:
        body_limit = "HARD LIMIT: 300 characters total (not words). Count characters carefully."
        subject_note = 'No subject line for connection requests — set "subject" to ""'
        return_format = '{\n  "subject": "",\n  "body": "<connection note, ≤300 characters>",\n  "word_count": <integer>,\n  "rationale": "<one sentence>"\n}'
    elif is_linkedin_dm:
        body_limit = "Body ≤75 words — casual LinkedIn DM style, no email formalities"
        subject_note = 'No subject line for LinkedIn DMs — set "subject" to ""'
        return_format = '{\n  "subject": "",\n  "body": "<LinkedIn DM, ≤75 words>",\n  "word_count": <integer>,\n  "rationale": "<one sentence>"\n}'
    else:
        body_limit = "Body ≤75 words — hard limit, count every word"
        subject_note = "Subject line: specific and curiosity-inducing — not 'Following up' or 'Job Opportunity'"
        return_format = '{\n  "subject": "<subject line>",\n  "body": "<email body, ≤75 words>",\n  "word_count": <integer>,\n  "rationale": "<one sentence: hook used and why>"\n}'

    prompt = f"""You are writing a networking outreach message for an executive job search.

SENDER PROFILE:
{profile}

{contact_info}
MESSAGE TYPE: {type_instruction}
{hook_instruction}
{ask_instruction}
Additional context: {context or 'None provided'}

STRICT DALTON RULES:
1. {body_limit}
2. First-person, direct voice — no corporate speak
3. At least half the words focus on the contact or their work, not Santiago
4. One specific Santiago credential woven in naturally (SoyYo, Avianca, Uff Móvil, MIT Sloan)
5. {subject_note}
6. FORBIDDEN: "hope this finds you", "excited to", "pick your brain", "circle back",
   "touch base", "synergy", "I'm looking for opportunities", "I'd love to connect"
7. DO NOT include a signature block — no "Santiago Aldana", no email address, no title line at the end.
8. If the contact is a 1st-degree connection or warmth is "warm", reference that shared context naturally.

Return JSON (no markdown):
{return_format}"""

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


# ── Follow-up Email Templates (No API cost) ─────────────────────────────────

FOLLOW_UP_TEMPLATES = {
    "day_3": {
        "subject": "Re: {original_subject}",
        "body": """Hi {first_name},

Just following up on my previous message. I'd love to hear your thoughts on {brief_context}.

Looking forward to connecting.

Best,
Santiago""",
    },
    "day_7": {
        "subject": "Re: {original_subject}",
        "body": """Hi {first_name},

I understand you're busy. If now isn't a good time, no worries—I'll leave this here. Feel free to reach out if you'd like to chat.

Best,
Santiago""",
    },
    "harvest": {
        "subject": "Quick check-in",
        "body": """Hi {first_name},

It's been {days_since} since we last connected. I wanted to see if there's been any movement on your end that we should discuss.

Looking forward to reconnecting.

Best,
Santiago""",
    },
}


def draft_followup_from_template(stage: str, outreach_record: dict) -> dict:
    """
    Generate follow-up email from template based on conversation stage.
    No API call — uses predefined templates for standard follow-ups.

    Args:
        stage: "day_3" | "day_7" | "harvest"
        outreach_record: Dict with company, contact_name, contact_role, sent_date, notes, etc.

    Returns:
        {subject, body, stage, template_used: True}
    """
    if stage not in FOLLOW_UP_TEMPLATES:
        return {"error": f"Unknown stage: {stage}"}

    template = FOLLOW_UP_TEMPLATES[stage]
    subject_template = template["subject"]
    body_template = template["body"]

    # Extract variables for interpolation
    first_name = outreach_record.get("contact_name", "").split()[0] or "there"
    original_subject = outreach_record.get("generated_subject", "our conversation")
    brief_context = outreach_record.get("contact_role", "the role")

    # Calculate days since sent
    from datetime import datetime, date
    sent_date_str = outreach_record.get("sent_date", "")
    try:
        sent_date = datetime.fromisoformat(sent_date_str).date()
        days_since = (date.today() - sent_date).days
    except (ValueError, TypeError):
        days_since = 0

    # Interpolate template variables
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


async def enhance_draft_with_context(
    draft_subject: str,
    draft_body: str,
    conversation_history: List[dict],
    stage: str = "follow_up",
) -> dict:
    """
    Optional on-demand enhancement: refine a template-based draft using full conversation context.
    Calls Claude Opus with conversation history (costs API token).

    Args:
        draft_subject: Template-generated subject line
        draft_body: Template-generated body
        conversation_history: List of previous messages [{date, from, subject, body_preview}, ...]
        stage: "day_3" | "day_7" | "harvest"

    Returns:
        {subject, body, reasoning, enhanced: True}
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    # Format conversation history for Claude
    history_text = "Previous conversation:\n\n"
    for msg in conversation_history[-5:]:  # Last 5 messages for context
        history_text += f"From: {msg.get('from_name', msg.get('from_email'))}\n"
        history_text += f"Date: {msg.get('date')}\n"
        history_text += f"Subject: {msg.get('subject')}\n"
        history_text += f"Message: {msg.get('body_preview')}\n\n"

    prompt = f"""You are refining a follow-up email to make it more contextual and personalized.

SENDER PROFILE:
{profile}

{history_text}

TEMPLATE DRAFT (generated automatically):
Subject: {draft_subject}
Body: {draft_body}

Your task: Refine this draft to:
1. Reference specific points from the conversation above
2. Maintain warm, conversational tone consistent with the thread
3. Keep it ≤100 words in body
4. Do NOT use corporate jargon or "synergy", "circle back", "pick your brain"
5. Do NOT add signature block

Return JSON:
{{
  "subject": "<refined subject>",
  "body": "<refined body, ≤100 words>",
  "reasoning": "<why this version is better: 1-2 sentences>"
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
        data["enhanced"] = True
        return data
    except Exception as e:
        return {
            "subject": draft_subject,
            "body": draft_body,
            "reasoning": f"Enhancement failed: {str(e)}",
            "enhanced": False,
        }


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
