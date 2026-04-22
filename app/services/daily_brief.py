"""
Daily Brief Engine — computes priority-ordered action list for today.
Called by GET /api/daily-brief
"""

from datetime import datetime
from sqlmodel import Session, select
from typing import List

from app.models import (
    OutreachRecord, Lead, Event, Application,
    ContentDraft, AITargetSuggestion, Company, Interview
)


def compute_daily_brief(session: Session) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    actions = []

    # ── Priority 1: Overdue follow-ups ────────────────────────────────────────
    overdue = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_3_due <= today,
        )
    ).all()

    for record in overdue:
        company = session.get(Company, record.company_id) if record.company_id else None
        days_overdue = _days_diff(record.follow_up_3_due, today)
        actions.append({
            "priority": 1,
            "action_type": "follow_up",
            "label": f"Follow up at {company.name if company else 'Unknown'}",
            "detail": f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue",
            "cta": "Draft follow-up",
            "company_id": record.company_id,
            "payload_id": record.id,
            "payload_type": "outreach",
        })

    # ── Priority 2: HOT leads (fit ≥ 65, recent, not yet applied) ────────────
    hot_leads = session.exec(
        select(Lead).where(
            Lead.fit_score >= 65,
            Lead.location_compatible == True,
            Lead.status == "active",
        ).order_by(Lead.fit_score.desc())
    ).all()

    for lead in hot_leads[:5]:  # show top 5 at most
        company = session.get(Company, lead.company_id) if lead.company_id else None
        actions.append({
            "priority": 2,
            "action_type": "hot_lead",
            "label": f"HOT match: {lead.title} at {company.name if company else 'Unknown'}",
            "detail": f"Fit: {lead.fit_score:.0f}% | {lead.location or 'Location unknown'}",
            "cta": "Review & Apply",
            "company_id": lead.company_id,
            "payload_id": lead.id,
            "payload_type": "lead",
        })

    # ── Priority 3: Events within 7 days ─────────────────────────────────────
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
        actions.append({
            "priority": 3,
            "action_type": "event",
            "label": f"Event: {event.name}",
            "detail": f"In {days_away} day{'s' if days_away != 1 else ''} — {event.meetings_booked} meetings booked",
            "cta": "Prepare attendee list",
            "payload_id": event.id,
            "payload_type": "event",
        })

    # ── Priority 4: High-motivation companies with no outreach started ────────
    active_companies = session.exec(
        select(Company).where(
            Company.is_archived == False,
            Company.motivation >= 8,
            Company.advocacy_score >= 7,
            Company.stage == "pool",
        ).order_by(Company.lamp_score.desc())
    ).all()

    for company in active_companies[:3]:
        actions.append({
            "priority": 4,
            "action_type": "start_outreach",
            "label": f"Start outreach: {company.name}",
            "detail": f"LAMP {company.lamp_score} | Motivation {company.motivation} | Strong advocacy",
            "cta": "Find contact & draft email",
            "company_id": company.id,
            "payload_id": company.id,
            "payload_type": "company",
        })

    # ── Priority 5: Interviews in next 48h ───────────────────────────────────
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
        actions.append({
            "priority": 5,
            "action_type": "interview_prep",
            "label": f"Interview prep: {company.name if company else 'Unknown'}",
            "detail": f"{interview.type} interview on {interview.scheduled_at[:10]}",
            "cta": "Generate prep brief",
            "company_id": company.id if company else None,
            "payload_id": interview.id,
            "payload_type": "interview",
        })

    # ── Priority 6: LinkedIn drafts with high score ───────────────────────────
    top_drafts = session.exec(
        select(ContentDraft).where(
            ContentDraft.status == "approved",
            ContentDraft.net_score >= 7.0,
        ).order_by(ContentDraft.net_score.desc())
    ).all()

    for draft in top_drafts[:2]:
        actions.append({
            "priority": 6,
            "action_type": "publish_content",
            "label": f"Publish LinkedIn post (score {draft.net_score:.1f})",
            "detail": draft.body[:80] + "…" if len(draft.body) > 80 else draft.body,
            "cta": "Review & Publish",
            "payload_id": draft.id,
            "payload_type": "content",
        })

    # ── Pending AI suggestions ────────────────────────────────────────────────
    suggestions = session.exec(
        select(AITargetSuggestion).where(AITargetSuggestion.reviewed == False)
    ).all()

    if suggestions:
        actions.append({
            "priority": 7,
            "action_type": "review_suggestions",
            "label": f"{len(suggestions)} new company suggestion{'s' if len(suggestions) != 1 else ''} to review",
            "detail": ", ".join(s.name for s in suggestions[:3]),
            "cta": "Review targets",
            "payload_id": None,
            "payload_type": "suggestions",
        })

    # Sort by priority
    actions.sort(key=lambda x: (x["priority"], -x.get("payload_id", 0) or 0))

    return {
        "date": today,
        "total_actions": len(actions),
        "overdue_count": sum(1 for a in actions if a["priority"] == 1),
        "actions": actions,
    }


def _days_diff(date_a: str, date_b: str) -> int:
    """Number of days from date_a to date_b (positive if b > a)."""
    try:
        a = datetime.strptime(date_a[:10], "%Y-%m-%d")
        b = datetime.strptime(date_b[:10], "%Y-%m-%d")
        return (b - a).days
    except Exception:
        return 0


def _add_days(date_str: str, days: int) -> str:
    from datetime import timedelta
    d = datetime.strptime(date_str[:10], "%Y-%m-%d")
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")
