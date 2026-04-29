"""
Daily Brief Engine — 3-section action list: Positions | Outreach | Events
Called by GET /api/daily-brief
"""

from datetime import datetime, timedelta
from sqlmodel import Session, select

from app.models import (
    OutreachRecord, Lead, Event, Application,
    ContentDraft, AITargetSuggestion, Company, Interview, Contact
)


def compute_daily_brief(session: Session) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    positions = []
    outreach = []
    events_section = []

    # ══════════════════════════════════════════════════════════════════════════
    # OUTREACH SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # Day-3 follow-ups due (not yet sent)
    day3_records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_3_due <= today,
            OutreachRecord.follow_up_3_sent == False,
        )
    ).all()

    for record in day3_records:
        company = session.get(Company, record.company_id) if record.company_id else None
        days_overdue = _days_diff(record.follow_up_3_due, today)
        outreach.append({
            "action_type": "follow_up_3",
            "label": f"Day 3 follow-up — {company.name if company else 'Unknown'}",
            "detail": f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue",
            "cta": "Draft follow-up",
            "company_id": record.company_id,
            "payload_id": record.id,
            "payload_type": "outreach",
            "followup_day": 3,
        })

    # Day-7 close-outs due (day3 already sent, day7 not yet sent)
    day7_records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_7_due <= today,
            OutreachRecord.follow_up_3_sent == True,
            OutreachRecord.follow_up_7_sent == False,
        )
    ).all()

    for record in day7_records:
        company = session.get(Company, record.company_id) if record.company_id else None
        days_overdue = _days_diff(record.follow_up_7_due, today)
        outreach.append({
            "action_type": "follow_up_7",
            "label": f"Day 7 close — {company.name if company else 'Unknown'}",
            "detail": f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue · polite close",
            "cta": "Draft closing note",
            "company_id": record.company_id,
            "payload_id": record.id,
            "payload_type": "outreach",
            "followup_day": 7,
        })

    # Warm path alerts — new 1st-degree contacts at funnel companies (last 7 days)
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    recent_warm = session.exec(
        select(Contact).where(
            Contact.connection_degree == 1,
            Contact.company_id != None,
            Contact.created_at >= seven_days_ago,
            Contact.outreach_status == "none",
        )
    ).all()

    for contact in recent_warm[:3]:
        company = session.get(Company, contact.company_id) if contact.company_id else None
        outreach.append({
            "action_type": "warm_path",
            "label": f"Warm path — {contact.name} at {company.name if company else 'Unknown'}",
            "detail": "New 1st-degree connection · reach out now",
            "cta": "Draft outreach",
            "company_id": contact.company_id,
            "payload_id": contact.id,
            "payload_type": "contact",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # POSITIONS SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # Monday LinkedIn import reminder
    if datetime.utcnow().weekday() == 0:
        positions.append({
            "action_type": "linkedin_import_reminder",
            "label": "Update your network map",
            "detail": "Export LinkedIn contacts → upload to Settings to find new warm paths",
            "cta": "Upload contacts",
            "payload_id": None,
            "payload_type": "settings",
            "instructions": (
                "1. linkedin.com → Me → Settings & Privacy\n"
                "2. Data Privacy → Get a copy of your data\n"
                "3. Select 'Connections' only → Request archive\n"
                "4. LinkedIn emails download link (≈10 min)\n"
                "5. Download zip → extract Connections.csv\n"
                "6. Come back → tap 'Upload contacts'"
            ),
        })

    # HOT leads — grouped by company
    hot_leads = session.exec(
        select(Lead).where(
            Lead.fit_score >= 65,
            Lead.location_compatible == True,
            Lead.status == "active",
        ).order_by(Lead.fit_score.desc())
    ).all()

    seen_companies: dict = {}
    for lead in hot_leads:
        cid = lead.company_id or 0
        if cid not in seen_companies:
            seen_companies[cid] = {"leads": [], "best_score": 0}
        seen_companies[cid]["leads"].append(lead)
        if (lead.fit_score or 0) > seen_companies[cid]["best_score"]:
            seen_companies[cid]["best_score"] = lead.fit_score or 0

    for cid, data in list(seen_companies.items())[:5]:
        company = session.get(Company, cid) if cid else None
        count = len(data["leads"])
        best = int(data["best_score"])
        cname = company.name if company else "Unknown"
        positions.append({
            "action_type": "hot_lead",
            "label": f"{count} HOT match{'es' if count > 1 else ''} at {cname}",
            "detail": f"Best fit: {best}% · {count} open position{'s' if count > 1 else ''}",
            "cta": "Review & Apply",
            "company_id": cid or None,
            "payload_id": cid or None,
            "payload_type": "company",
        })

    # High-motivation companies ready for outreach
    active_companies = session.exec(
        select(Company).where(
            Company.is_archived == False,
            Company.motivation >= 8,
            Company.advocacy_score >= 7,
            Company.stage == "pool",
        ).order_by(Company.lamp_score.desc())
    ).all()

    for company in active_companies[:3]:
        positions.append({
            "action_type": "start_outreach",
            "label": f"Start outreach: {company.name}",
            "detail": f"LAMP {company.lamp_score} · Motivation {company.motivation} · Strong advocacy",
            "cta": "Find contact & draft email",
            "company_id": company.id,
            "payload_id": company.id,
            "payload_type": "company",
        })

    # Approved LinkedIn content drafts
    top_drafts = session.exec(
        select(ContentDraft).where(
            ContentDraft.status == "approved",
            ContentDraft.net_score >= 7.0,
        ).order_by(ContentDraft.net_score.desc())
    ).all()

    for draft in top_drafts[:2]:
        positions.append({
            "action_type": "publish_content",
            "label": f"Publish LinkedIn post (score {draft.net_score:.1f})",
            "detail": draft.body[:80] + "…" if len(draft.body) > 80 else draft.body,
            "cta": "Review & Publish",
            "payload_id": draft.id,
            "payload_type": "content",
        })

    # Pending AI suggestions
    suggestions = session.exec(
        select(AITargetSuggestion).where(AITargetSuggestion.reviewed == False)
    ).all()

    if suggestions:
        positions.append({
            "action_type": "review_suggestions",
            "label": f"{len(suggestions)} new company suggestion{'s' if len(suggestions) != 1 else ''} to review",
            "detail": ", ".join(s.name for s in suggestions[:3]),
            "cta": "Review targets",
            "payload_id": None,
            "payload_type": "suggestions",
        })

    # Upcoming interviews
    in_2_days = _add_days(today, 2)
    upcoming_interviews = session.exec(
        select(Interview).where(
            Interview.scheduled_at >= today,
            Interview.scheduled_at <= in_2_days + "T23:59:59",
        )
    ).all()

    for interview in upcoming_interviews:
        app = session.get(Application, interview.application_id)
        company = session.get(Company, app.company_id) if app else None
        positions.append({
            "action_type": "interview_prep",
            "label": f"Interview prep: {company.name if company else 'Unknown'}",
            "detail": f"{interview.type} interview on {interview.scheduled_at[:10]}",
            "cta": "Generate prep brief",
            "company_id": company.id if company else None,
            "payload_id": interview.id,
            "payload_type": "interview",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # EVENTS SECTION
    # ══════════════════════════════════════════════════════════════════════════

    in_7_days = _add_days(today, 7)
    upcoming_events = session.exec(
        select(Event).where(
            Event.date >= today,
            Event.date <= in_7_days,
        ).order_by(Event.net_score.desc())
    ).all()

    _noise_phrases = [
        'sticker', 'crafts', 'yoga', 'cooking', 'art class', 'dance',
        'wedding', 'birthday', 'baby shower', 'wine tasting', 'painting',
        'knitting', 'lisa frank', 'rainbow', 'diy workshop', 'datathon',
        'applying ai', 'women applying', 'happy hour', 'physical ai happy',
        'knowledge graph', 'research copilot',
    ]
    _relevant_kw = [
        'fintech', 'payments', 'banking', 'identity', 'fraud', 'embedded',
        'agentic', 'startup', 'venture', 'cto', 'cpo', 'executive',
        'mit sloan', 'mit imagination', 'sloan', 'techstars', 'emtech',
        'series b', 'series c', 'smarter faster', 'nacha', 'ny fintech',
        'fintech week',
    ]

    def _is_relevant(e):
        text = f"{e.name or ''} {e.description or ''}".lower()
        if any(phrase in text for phrase in _noise_phrases):
            return False
        if e.category and e.category.upper() == 'STRATEGIC':
            return True
        if any(kw in text for kw in _relevant_kw):
            return True
        return (e.net_score or 0) >= 7.0

    for event in upcoming_events:
        if not _is_relevant(event):
            continue
        days_away = _days_diff(today, event.date)
        events_section.append({
            "action_type": "event",
            "label": f"Event: {event.name}",
            "detail": f"In {days_away} day{'s' if days_away != 1 else ''} · {event.location or 'Boston'}",
            "cta": "View & Register",
            "event_id": event.id,
            "payload_id": event.id,
            "payload_type": "event",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # RETURN 3-SECTION RESPONSE
    # ══════════════════════════════════════════════════════════════════════════

    total = len(positions) + len(outreach) + len(events_section)
    overdue = len([a for a in outreach if a["action_type"] in ("follow_up_3", "follow_up_7")])

    return {
        "date": today,
        "total_actions": total,
        "overdue_count": overdue,
        "positions": positions,
        "outreach": outreach,
        "events": events_section,
        # Legacy flat list for backwards compat with any old clients
        "actions": positions + outreach + events_section,
    }


def _days_diff(date_a: str, date_b: str) -> int:
    try:
        a = datetime.strptime(date_a[:10], "%Y-%m-%d")
        b = datetime.strptime(date_b[:10], "%Y-%m-%d")
        return (b - a).days
    except Exception:
        return 0


def _add_days(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")
