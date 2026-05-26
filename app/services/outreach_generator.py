"""
Outreach Generator — drafts, context assembly, and AI-powered escalation drafts.
"""

from typing import Optional, List


# ── Outreach Context Assembly ─────────────────────────────────────────────────

TYPE_INSTRUCTIONS = {
    "cold": (
        "This is a cold email to someone who does not know Santiago. "
        "Do NOT open with a generic connection claim. Instead, lead with a specific, current detail "
        "about what this company is doing or facing right now — pulled from the intel_summary — "
        "filtered through the lens of what matters most to someone in this contact's specific role. "
        "The intel may arrive as structured sections (RECENT NEWS, CONTACTS, OUTREACH, OPEN ROLES) "
        "or as narrative prose. In either case, extract one concrete fact, not a category label. "
        "Apply a role-relevance filter: a product launch matters more to a CPO than a CFO; "
        "a funding round matters more to a CFO than a CTO. If no detail passes that filter, "
        "infer the most likely pressure point for this title given the company stage and sector. "
        "Do not fabricate shared history."
    ),
    "event_met": (
        "This is a follow-up email to someone Santiago met in person. They already know who he is. "
        "Do NOT re-establish credentials — his profile does that. "
        "Open by anchoring on one specific thing from the meeting note: something the contact said, "
        "a question they raised, or a point that landed. The recipient should recognize exactly "
        "which conversation this is from. Then bridge to a peer-level observation from Santiago's "
        "experience that connects to what they discussed. End with a question that continues the "
        "thread, not one that opens a new topic. Offer a 30-minute call — not 15. "
        "Do not use 'Great meeting you' or 'Really enjoyed our conversation' as openers."
    ),
    "followup": "Acknowledge briefly that you reached out before, add new value, re-ask.",
    "linkedin_dm": (
        "This is a LinkedIn DIRECT MESSAGE after a connection was accepted. "
        "The recipient can see Santiago's full LinkedIn profile — do not use words to establish "
        "credentials that his profile already shows. Use that space for substance instead. "
        "Conversational register, short sentences, no corporate vocabulary. "
        "Lead with one specific, current detail about their company filtered through their role "
        "(same dual-format intel handling and role-relevance filter as cold email). "
        "Follow with a direct question asking for their perspective on that topic. "
        "End with an offer of a 20-minute call framed as continuing the topic, not a separate ask. "
        "Do NOT end with 'Open to a quick call?' — that phrase marks the message as a template. "
        "No subject line. No em dashes, en dashes, or hyphens. No signature block."
    ),
    "connection_request": (
        "LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total including spaces. "
        "One sentence only. Reference one specific thing about their work or company right now "
        "that someone in their role would recognize as true about their own situation. "
        "Do not introduce Santiago by name or title. Do not ask for a call. Do not end with a question. "
        "End with: 'Would value the connection.' "
        "No em dashes, en dashes, or hyphens."
    ),
    "connection_request_a": (
        "LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total including spaces. "
        "One sentence only. Reference one specific thing about their work or company right now "
        "that someone in their role would recognize as true about their own situation. "
        "Do not introduce Santiago by name or title. Do not ask for a call. Do not end with a question. "
        "End with: 'Would value the connection.' "
        "No em dashes, en dashes, or hyphens."
    ),
    "connection_request_b": (
        "LinkedIn CONNECTION REQUEST NOTE. HARD LIMIT: 300 characters total including spaces. "
        "One sentence only. Reference one specific thing about their work or company right now "
        "that someone in their role would recognize as true about their own situation. "
        "Do not introduce Santiago by name or title. Do not ask for a call. Do not end with a question. "
        "End with: 'Would value the connection.' "
        "No em dashes, en dashes, or hyphens."
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


SANTIAGO_PROFILE = {
    "name": "Santiago Aldana",
    "current_role": "Chief Product & Solutions Officer, St. Mary's Credit Union (SMCU)",
    "managing_partner": "AI Data Solutions — exclusive LATAM distribution of Maven AGI",
    "target_roles": ["CEO", "COO", "CPO", "SVP Product", "SVP Payments", "SVP Embedded Banking"],
    "target_sectors": ["Payments", "Embedded Banking", "Agentic AI", "Digital Identity", "BaaS"],
    "positioning": (
        "Enterprise Whisperer / Speedboat — brings enterprise discipline to growth-stage FinTech. "
        "Turns regulated complexity into competitive moat."
    ),
    "key_credentials": [
        "CEO SoyYo (2020-2024) — digital identity platform, 3M+ users, sold to Redeban (Colombia's leading PSP)",
        "CDTO Avianca (2017-2019) — $110M IT budget, $700-800M annual digital revenue, 47% of sales migrated to digital",
        "CEO Uff! Movil (2010-2015) — LatAm's first MVNO, 400K customers, sold to Bancolombia at $18M",
        "CIO Telefonica (2004-2009) — 60M EUR IT transformation across 5 countries in 17 months",
        "MIT Sloan MBA — Strategy, Innovation and Technology",
    ],
    "board_roles": ["Tuya Credit Card (Open Banking)", "Colombia Fintech (regulatory)", "Zulu (cross-border crypto)"],
    "target_company_stage": "Series B-D FinTech or growth-stage payments/AI",
    "geography": "Boston, MA — open to remote/hybrid",
    "outreach_style": "Dalton method — ultra-short, specific ask, no fluff, no em dashes",
}

GENERATION_INSTRUCTIONS = (
    "Write a Dalton 6-point outreach message using ALL of the data above. This must feel like it was written specifically for this person — not a template.\n\n"
    "PERSONALIZATION (do all of these):\n"
    "- Read the company intel_summary carefully. Find one specific, current detail about what this company is doing or facing right now — use that as the hook, not a generic industry observation.\n"
    "- Look at the contact's title and role. What is the hardest part of their job right now given the company's situation? Orient the message around their world, not Santiago's.\n"
    "- Pick the one credential from Santiago's profile that is most directly relevant to THIS person's specific challenges — not the most impressive credential in general.\n"
    "- If relationship_notes or met_via is present, reference it concretely.\n"
    "- If a prior_message exists, this is a follow-up — acknowledge it briefly without being apologetic.\n\n"
    "DALTON RULES (non-negotiable):\n"
    "- Body ≤75 words (300 chars max for connection requests)\n"
    "- Subject line: their experience or role at this company, not Santiago's ask\n"
    "- At least half the words are about THEM\n"
    "- End with an open question, not a statement\n"
    "- Ask for advice or insight, never a job or introduction\n"
    "- No em dashes, en dashes, or hyphens anywhere in the text\n"
    "- Forbidden phrases: 'hope this finds you', 'I am reaching out', 'opportunity', 'resume', 'job search', 'excited to', 'would love to'\n\n"
    "Return ONLY valid JSON in this exact format:\n"
    '{"subject": "<subject line>", "body": "<email body, ≤75 words, plain text, no markdown>"}'
)


async def generate_escalation_draft(
    contact,
    company,
    prior_message: Optional[str] = None,
    email_type: str = "cold",
) -> Optional[dict]:
    """
    Call Claude Haiku to generate a personalized escalation draft.
    Returns {"subject": ..., "body": ...} or None on failure.
    """
    import json
    import anthropic

    contact_info = {}
    if contact:
        contact_info = {
            "name": contact.name,
            "title": contact.title or "unknown title",
            "connection_degree": getattr(contact, "connection_degree", "unknown"),
            "warmth": getattr(contact, "warmth", "cold"),
            "met_via": getattr(contact, "met_via", None),
            "relationship_notes": getattr(contact, "relationship_notes", None),
        }

    company_info = {
        "name": company.name if company else "unknown",
        "intel_summary": (getattr(company, "intel_summary", None) or "")[:1500],
        "stage": getattr(company, "stage", None),
    }

    # For event_met, inject the meeting note from prior_message field if present.
    # The caller passes context (meeting note) via prior_message for this type.
    context = {
        "company": company_info,
        "contact": contact_info,
        "email_type": email_type,
        "type_instructions": TYPE_INSTRUCTIONS.get(email_type, TYPE_INSTRUCTIONS["cold"]),
        "santiago_profile": SANTIAGO_PROFILE,
    }
    if email_type == "event_met":
        context["meeting_note"] = prior_message or ""
    else:
        context["prior_message"] = prior_message

    # Use Sonnet for high-stakes single-shot moments (cold, event_met, linkedin_dm).
    # Haiku is sufficient for escalation drafts where the fallback template is strong.
    sonnet_types = {"cold", "event_met", "linkedin_dm"}
    model = "claude-sonnet-4-6" if email_type in sonnet_types else "claude-haiku-4-5-20251001"

    prompt = f"Here is the outreach context:\n\n{json.dumps(context, indent=2)}\n\n{GENERATION_INSTRUCTIONS}"

    try:
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(raw)
        if "subject" in result and "body" in result:
            return result
    except Exception:
        pass

    return None


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
            "body": "Hi {first_name},\n\nJust wanted to make sure my note didn't get buried. Would love to hear your perspective whenever you have a few minutes.",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nQuería asegurarme de que mi mensaje no se perdiera. Me encantaría escuchar tu perspectiva cuando tengas unos minutos.",
        },
    },
    "day_7": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nI don't mean to be a bother. If I don't hear back, I'll take that as a no and won't follow up again. I genuinely appreciated the chance to reach out.",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nNo quiero ser un inconveniente. Si no recibo respuesta, lo tomaré como un no y no volveré a escribir. Genuinamente aprecié la oportunidad de contactarte.",
        },
    },
    "harvest": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nCircling back one last time. If there's ever a moment to connect, I'd welcome it.",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nVuelvo a escribirte una última vez. Si en algún momento hay oportunidad de conversar, lo agradecería mucho.",
        },
    },
    "post_meeting": {
        "en": {
            "subject": "Great talking with you",
            "body": "Hi {first_name},\n\nYou gave me a lot to think about. Thank you so much for your time.\n\nWould it be okay if I reached back out to you after I've had a chance to reflect?\n\nSantiago",
        },
        "es": {
            "subject": "Fue un placer hablar contigo",
            "body": "Hola {first_name},\n\nMe diste mucho en qué pensar. Muchas gracias por tu tiempo.\n\n¿Estaría bien si me comunico contigo una vez que haya reflexionado un poco?\n\nSantiago",
        },
    },
    "post_meeting_2": {
        "en": {
            "subject": "Re: {original_subject}",
            "body": "Hi {first_name},\n\nI've had a chance to reflect on our conversation. It was genuinely helpful.\n\nI wanted to ask: if you were in my position, are there any resources, people, or next steps you'd recommend?\n\nThanks again,\nSantiago",
        },
        "es": {
            "subject": "Re: {original_subject}",
            "body": "Hola {first_name},\n\nHe tenido tiempo para reflexionar sobre nuestra conversación. Fue muy útil.\n\nQuería preguntarte: si estuvieras en mi posición, ¿hay algún recurso, persona o próximo paso que recomendarías?\n\nGracias de nuevo,\nSantiago",
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


# ── Initial Outreach Templates ────────────────────────────────────────────────

INITIAL_OUTREACH_TEMPLATES = {
    "cold": {
        "subject": "Quick question — {company}",
        "body": (
            "Hi {first_name},\n\n"
            "{hook_or_context}"
            "I've been following {company}'s work and see strong alignment with my background "
            "in FinTech, AI and payments across Latin America.\n\n"
            "Would love your perspective on {ask_short}. Open to a quick call?\n\nBest,\nSantiago"
        ),
    },
    "event_met": {
        "subject": "Great meeting you — {event_ref}",
        "body": (
            "Hi {first_name},\n\n"
            "Really enjoyed our conversation at {event_ref}. {context_line}"
            "Your work at {company} resonates with what I've been building in agentic finance.\n\n"
            "Would love to continue the conversation. Open to a quick call?\n\nBest,\nSantiago"
        ),
    },
    "followup": {
        "subject": "Re: Quick question — {company}",
        "body": (
            "Hi {first_name},\n\n"
            "Following up on my note from last week. {context_line}"
            "Still very interested in {company}'s direction. Happy to connect at your convenience.\n\nBest,\nSantiago"
        ),
    },
    "linkedin_dm": {
        "subject": "",
        "body": (
            "Hi {first_name} — {hook_or_context}"
            "Really admire what {company} is building. "
            "Would love to hear your take on {ask_short}. Open to a quick call?"
        ),
    },
}


def draft_initial_outreach_from_template(
    company,
    contact=None,
    email_type: str = "cold",
    context: Optional[str] = None,
    hook: Optional[str] = None,
    ask: Optional[str] = None,
) -> dict:
    """Template-based initial outreach draft. No API call."""
    tpl = INITIAL_OUTREACH_TEMPLATES.get(email_type) or INITIAL_OUTREACH_TEMPLATES["cold"]

    first_name = contact.name.split()[0] if contact and contact.name else "there"
    company_name = company.name if company else "your company"

    met_via = getattr(contact, "met_via", None) if contact else None
    relationship_notes = getattr(contact, "relationship_notes", None) if contact else None
    event_ref = met_via or "a recent event"

    ctx_text = (
        context
        or (f"Met via {met_via}. {relationship_notes}" if met_via and relationship_notes else None)
        or (f"Met via {met_via}" if met_via else None)
        or hook
        or ""
    )
    hook_or_context = (ctx_text.rstrip(".") + ". ") if ctx_text else ""
    context_line = hook_or_context

    ask_short = ask.rstrip(".?").lower() if ask else "where you see the space heading"

    subject = tpl["subject"].format(
        company=company_name, first_name=first_name, event_ref=event_ref
    )
    body = tpl["body"].format(
        first_name=first_name, company=company_name,
        hook_or_context=hook_or_context, context_line=context_line,
        ask_short=ask_short, event_ref=event_ref,
    )

    return {
        "subject": subject,
        "body": body,
        "word_count": len(body.split()),
        "rationale": f"Template draft ({email_type}) — edit or refine before sending.",
        "template_used": True,
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
