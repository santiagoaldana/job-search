"""
Daily Brief Engine — 3-section action list: Positions | Outreach | Events
Called by GET /api/daily-brief
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlmodel import Session, select, or_

_EASTERN = ZoneInfo("America/New_York")

def _now_eastern() -> datetime:
    return datetime.now(_EASTERN)

from app.models import (
    OutreachRecord, Lead, Event, Application,
    ContentDraft, AITargetSuggestion, Company, Interview, Contact,
    DismissedBriefAction, ConversationMessage, StrategyConfig, GmailSyncState,
)
from app.services.email_finder import determine_next_step as _contact_next_step



def compute_daily_brief(session: Session) -> dict:
    today = _now_eastern().strftime("%Y-%m-%d")
    positions = []
    outreach = []
    events_section = []

    dismissed = {
        (d.action_type, d.payload_id)
        for d in session.exec(select(DismissedBriefAction)).all()
    }

    # Gmail sync health check — warn if last sync failed or is stale (>25h)
    sync_state = session.exec(select(GmailSyncState)).first()
    if sync_state:
        sync_summary = json.loads(sync_state.last_sync_summary or "{}")
        sync_error = sync_summary.get("error")
        hours_since_sync = (datetime.utcnow() - datetime.fromisoformat(sync_state.last_poll_at)).total_seconds() / 3600 if sync_state.last_poll_at else 999
        if sync_error or hours_since_sync > 25:
            detail = sync_error if sync_error else f"Last successful sync {int(hours_since_sync)}h ago — emails may be missed"
            outreach.append({
                "action_type": "sync_warning",
                "label": "Gmail sync issue — data may be stale",
                "detail": detail,
                "cta": "Re-sync",
                "payload_id": None,
                "payload_type": None,
            })

    # ══════════════════════════════════════════════════════════════════════════
    # OUTREACH SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # New replies detected via Gmail sync in last 48h — highest priority cards
    forty_eight_hours_ago = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    recent_reply_records = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.response_status == "positive")
        .where(OutreachRecord.updated_at >= forty_eight_hours_ago)
        .order_by(OutreachRecord.updated_at.desc())  # type: ignore[arg-type]
    ).all()

    for record in recent_reply_records[:5]:
        latest_reply_msg = session.exec(
            select(ConversationMessage)
            .where(ConversationMessage.outreach_record_id == record.id)
            .where(ConversationMessage.message_type == "reply")
            .order_by(ConversationMessage.message_date.desc())  # type: ignore[arg-type]
        ).first()
        if not latest_reply_msg:
            continue
        company = session.get(Company, record.company_id) if record.company_id else None
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else "Unknown"))
        snippet = (latest_reply_msg.body_full or "")[:120].replace("\n", " ").strip()
        outreach.append({
            "action_type": "new_reply",
            "label": f"Reply received — {who}",
            "detail": f'"{snippet}..."' if snippet else "New reply in your inbox",
            "cta": "Draft response",
            "company_id": record.company_id,
            "contact_id": record.contact_id,
            "contact_name": contact.name if contact else None,
            "company_name": company.name if company else None,
            "payload_id": record.id,
            "payload_type": "outreach",
        })

    # Post-meeting follow-ups due (meeting has passed, thank-you not yet sent)
    met_records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.meeting_date != None,
            OutreachRecord.post_meeting_followup_sent == False,
            OutreachRecord.meeting_date <= today,
        )
    ).all()

    for record in met_records:
        company = session.get(Company, record.company_id) if record.company_id else None
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else "Unknown"))
        days_ago = _days_diff(record.meeting_date, today)
        detail_time = "today" if days_ago == 0 else ("yesterday" if days_ago == 1 else f"{days_ago} days ago")
        outreach.append({
            "action_type": "post_meeting_followup",
            "label": f"Follow up after meeting — {who}",
            "detail": f"Met {detail_time} · send thank-you note",
            "cta": "Draft follow-up",
            "company_id": record.company_id,
            "contact_id": record.contact_id,
            "contact_name": contact.name if contact else None,
            "company_name": company.name if company else None,
            "payload_id": record.id,
            "payload_type": "outreach",
            "followup_day": 0,
        })

    # Post-meeting second follow-up due (D+3 after thank-you sent — resources/recommendations ask)
    met_2_records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.post_meeting_2_due != None,
            OutreachRecord.post_meeting_2_sent == False,
            OutreachRecord.post_meeting_2_due <= today,
        )
    ).all()

    for record in met_2_records:
        company = session.get(Company, record.company_id) if record.company_id else None
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else "Unknown"))
        outreach.append({
            "action_type": "post_meeting_followup_2",
            "label": f"Reach back out — {who}",
            "detail": "Ask for resources and recommendations",
            "cta": "Draft follow-up",
            "company_id": record.company_id,
            "contact_id": record.contact_id,
            "contact_name": contact.name if contact else None,
            "company_name": company.name if company else None,
            "payload_id": record.id,
            "payload_type": "outreach",
            "followup_day": -1,
        })

    # LinkedIn acceptances — surface persistently until DM is sent (follow_up_3_sent marks it done)
    recent_accepted = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.linkedin_accepted == True)
        .where(OutreachRecord.follow_up_3_sent == False)
        .order_by(OutreachRecord.updated_at.desc())  # type: ignore[arg-type]
    ).all()

    for record in recent_accepted[:3]:
        if record.escalation_snooze_until and record.escalation_snooze_until > today:
            continue
        company = session.get(Company, record.company_id) if record.company_id else None
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else "Unknown"))
        outreach.append({
            "action_type": "linkedin_accepted",
            "label": f"LinkedIn accepted — {who}",
            "detail": "Connection accepted — send your first outreach DM",
            "cta": "Draft DM",
            "company_id": record.company_id,
            "contact_id": record.contact_id,
            "contact_name": contact.name if contact else None,
            "company_name": company.name if company else None,
            "payload_id": record.id,
            "payload_type": "outreach",
            "escalation_channel": record.escalation_channel,
            "escalation_snooze_until": record.escalation_snooze_until,
        })

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
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        days_sent = _days_diff(record.sent_at, today)
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else 'Unknown'))

        if record.channel == "linkedin" and record.linkedin_accepted is None:
            # Skip if snoozed
            if record.escalation_snooze_until and record.escalation_snooze_until > today:
                continue
            # Skip if an email escalation was already sent for this contact
            if record.contact_id:
                email_escalation = session.exec(
                    select(OutreachRecord).where(
                        OutreachRecord.contact_id == record.contact_id,
                        OutreachRecord.channel == "email",
                        OutreachRecord.sent_at > (record.sent_at or ""),
                    )
                ).first()
                if email_escalation:
                    continue
            next_step = _contact_next_step(contact, company) if contact else {"action": "prompt_manual_email", "guessed_email": None}
            outreach.append({
                "action_type": "linkedin_not_accepted",
                "label": f"LinkedIn not accepted — {who}",
                "detail": f"{days_sent} day{'s' if days_sent != 1 else ''} with no response · Gmail checked",
                "cta": "Escalate to email",
                "company_id": record.company_id,
                "contact_id": record.contact_id,
                "contact_name": contact.name if contact else None,
                "contact_title": contact.title if contact else None,
                "company_name": company.name if company else None,
                "intel_summary": company.intel_summary if company else None,
                "payload_id": record.id,
                "payload_type": "outreach",
                "next_step": next_step,
                "days_sent": days_sent,
                "escalation_channel": record.escalation_channel,
                "escalation_snooze_until": record.escalation_snooze_until,
            })
        elif record.channel == "linkedin" and record.linkedin_accepted == True:
            continue  # handled by the persistent linkedin_accepted card above
        else:
            # Skip if contact is an active champion with a check-in due today — champion_checkin card takes priority
            if contact and contact.is_champion and contact.next_checkin_date and contact.next_checkin_date <= today:
                continue
            outreach.append({
                "action_type": "follow_up_3",
                "label": f"Day 3 follow-up — {who}",
                "detail": f"{days_sent} day{'s' if days_sent != 1 else ''} overdue",
                "cta": "Draft follow-up",
                "company_id": record.company_id,
                "contact_id": contact.id if contact else None,
                "contact_name": contact.name if contact else None,
                "contact_title": contact.title if contact else None,
                "is_champion": contact.is_champion if contact else False,
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
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        days_sent = _days_diff(record.sent_at, today)
        who = f"{contact.name} at {company.name}" if contact and company else (contact.name if contact else (company.name if company else 'Unknown'))

        # LinkedIn-only outreach with no acceptance: not an email close, skip
        if record.channel == "linkedin" and record.linkedin_accepted is None:
            continue

        # Skip if contact is an active champion with a check-in due today
        if contact and contact.is_champion and contact.next_checkin_date and contact.next_checkin_date <= today:
            continue

        outreach.append({
            "action_type": "follow_up_7",
            "label": f"Day 7 close — {who}",
            "detail": f"{days_sent} day{'s' if days_sent != 1 else ''} overdue · polite close",
            "cta": "Draft closing note",
            "company_id": record.company_id,
            "contact_id": contact.id if contact else None,
            "contact_name": contact.name if contact else None,
            "contact_title": contact.title if contact else None,
            "is_champion": contact.is_champion if contact else False,
            "linkedin_accepted": record.linkedin_accepted,
            "payload_id": record.id,
            "payload_type": "outreach",
            "followup_day": 7,
        })

    # Auto-ghost: both follow-ups sent, still pending, 14+ days since Day 7 sent
    ghost_cutoff = (_now_eastern() - timedelta(days=14)).strftime("%Y-%m-%d")
    stale_records = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_3_sent == True,
            OutreachRecord.follow_up_7_sent == True,
            OutreachRecord.follow_up_7_due <= ghost_cutoff,
        )
    ).all()
    for record in stale_records:
        record.response_status = "ghosted"
        record.updated_at = datetime.utcnow().isoformat()
        session.add(record)
    if stale_records:
        session.commit()

    # Champion check-ins due today
    champion_due = session.exec(
        select(Contact).where(
            Contact.is_champion == True,
            Contact.next_checkin_date != None,
            Contact.next_checkin_date <= today,
        )
    ).all()

    for contact in champion_due:
        company = session.get(Company, contact.company_id) if contact.company_id else None
        who = f"{contact.name} at {company.name}" if company else contact.name
        outreach.append({
            "action_type": "champion_checkin",
            "label": f"Check in — {who}",
            "detail": "Scheduled check-in",
            "cta": "Log outcome",
            "company_id": contact.company_id,
            "contact_id": contact.id,
            "contact_name": contact.name,
            "company_name": company.name if company else None,
            "champion_notes": contact.champion_notes,
            "next_checkin_date": contact.next_checkin_date,
            "contact_email": contact.email if not getattr(contact, "email_invalid", False) else None,
            "payload_id": contact.id,
            "payload_type": "contact",
        })

    # Warm path alerts — 1st-degree contacts at funnel companies with no outreach taken yet.
    # Surfaces every day until the user acts (logs outreach, marks champion, or sets a follow-up date).
    # snooze_until hides the card until that date; null means surface every day.
    today_date = _now_eastern().date()

    recent_warm = session.exec(
        select(Contact).where(
            Contact.connection_degree == 1,
            Contact.company_id != None,
            Contact.outreach_status == "none",
            Contact.is_champion == False,
        )
    ).all()
    recent_warm = [c for c in recent_warm if not c.snooze_until or c.snooze_until <= today_date.isoformat()]

    high_motivation_ids = {
        c.id for c in session.exec(select(Company).where(Company.motivation >= 7, Company.is_archived == False)).all()
    }
    contacted_contact_ids = {
        r.contact_id for r in session.exec(select(OutreachRecord).where(OutreachRecord.contact_id != None)).all()
    }
    recent_warm = [c for c in recent_warm if c.company_id in high_motivation_ids and c.id not in contacted_contact_ids]

    for contact in recent_warm[:3]:
        company = session.get(Company, contact.company_id) if contact.company_id else None
        intro_detail = None
        if contact.introduced_by_contact_id:
            introducer = session.get(Contact, contact.introduced_by_contact_id)
            if introducer:
                intro_company = session.get(Company, introducer.company_id) if introducer.company_id else None
                intro_at = f" at {intro_company.name}" if intro_company else ""
                intro_detail = f"Intro via {introducer.name}{intro_at}"
        detail = intro_detail or contact.relationship_notes or "New 1st-degree connection · reach out now"
        outreach.append({
            "action_type": "warm_path",
            "label": f"New connection — {contact.name} at {company.name if company else 'Unknown'}",
            "detail": detail,
            "cta": "Draft outreach",
            "company_id": contact.company_id,
            "payload_id": contact.id,
            "payload_type": "contact",
            "relationship_notes": contact.relationship_notes or "",
            "intel_summary": company.intel_summary if company else None,
        })

    # Bounce retry — contacts with invalid email that still have untried patterns
    bounced_contacts = session.exec(
        select(Contact).where(
            Contact.email_invalid == True,
            Contact.company_id != None,
        )
    ).all()
    for contact in bounced_contacts[:3]:
        company = session.get(Company, contact.company_id) if contact.company_id else None
        ns = _contact_next_step(contact, company)
        if ns["action"] == "draft_email_guessed" and ns.get("guessed_email"):
            outreach.append({
                "action_type": "email_bounce_retry",
                "label": f"Email bounced — try next pattern for {contact.name}",
                "detail": f"Next guess: {ns['guessed_email']} (unverified)",
                "cta": "Try new email",
                "company_id": contact.company_id,
                "payload_id": contact.id,
                "payload_type": "contact",
                "guessed_email": ns["guessed_email"],
            })
        elif ns["action"] in ("draft_linkedin_dm", "prompt_manual_email"):
            outreach.append({
                "action_type": "try_linkedin_dm",
                "label": f"All email patterns tried — reach out via LinkedIn for {contact.name}",
                "detail": f"at {company.name if company else 'Unknown'}",
                "cta": "Draft LinkedIn DM",
                "company_id": contact.company_id,
                "payload_id": contact.id,
                "payload_type": "contact",
            })

    # Call as last resort — contact has phone, email exhausted (invalid or all patterns tried),
    # LinkedIn not connected, and 14+ days since last outreach attempt
    call_cutoff = (_now_eastern() - timedelta(days=14)).strftime("%Y-%m-%d")
    phone_contacts = session.exec(
        select(Contact).where(
            Contact.phone != None,
            Contact.email_invalid == True,
        )
    ).all()
    for contact in phone_contacts[:2]:
        company = session.get(Company, contact.company_id) if contact.company_id else None
        latest = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == contact.id)
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if not latest or (latest.sent_at or "") > call_cutoff:
            continue
        if ("call", contact.id) in dismissed:
            continue
        outreach.append({
            "action_type": "call",
            "label": f"Call — {contact.name}" + (f" at {company.name}" if company else ""),
            "detail": f"Email exhausted · phone: {contact.phone}",
            "cta": "Get call script",
            "company_id": contact.company_id,
            "contact_id": contact.id,
            "contact_name": contact.name,
            "contact_title": contact.title,
            "phone": contact.phone,
            "payload_id": contact.id,
            "payload_type": "contact",
        })

    # LinkedIn DM follow-up — Day 7 passed, still pending, no DM record yet
    # Use only the most recent qualifying record per contact to avoid surfacing
    # stale records from duplicate contacts.
    needs_dm_all = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.response_status == "pending",
            OutreachRecord.follow_up_7_sent == True,
            OutreachRecord.channel == "email",
            OutreachRecord.follow_up_7_due <= today,
            or_(
                OutreachRecord.escalation_snooze_until == None,
                OutreachRecord.escalation_snooze_until <= today,
            ),
        ).order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
    ).all()
    # Dedup: keep only the most recent record per (company_id, contact_id) pair
    seen_dm_keys: set = set()
    needs_dm = []
    for r in needs_dm_all:
        key = (r.company_id, r.contact_id)
        if key not in seen_dm_keys:
            seen_dm_keys.add(key)
            needs_dm.append(r)

    seen_dm_companies: set = set()
    for record in needs_dm[:3]:
        # Skip if we've already added a DM card for this company (handles duplicate contacts)
        if record.company_id in seen_dm_companies:
            continue
        contact = session.get(Contact, record.contact_id) if record.contact_id else None
        company = session.get(Company, record.company_id) if record.company_id else None
        # Only surface if contact is 1st-degree (can DM them)
        if contact and contact.connection_degree == 1:
            seen_dm_companies.add(record.company_id)
            who = f"{contact.name} at {company.name}" if company else (contact.name if contact else 'Unknown')
            outreach.append({
                "action_type": "try_linkedin_dm",
                "label": f"No email reply — try LinkedIn DM for {who}",
                "detail": "Both email follow-ups sent · switch to LinkedIn",
                "cta": "Draft LinkedIn DM",
                "company_id": record.company_id,
                "payload_id": record.id,
                "payload_type": "outreach",
            })


    # Contact gap — high-motivation companies with no contacts and no active outreach
    active_company_ids_with_outreach = {
        r.company_id for r in session.exec(
            select(OutreachRecord).where(OutreachRecord.response_status == "pending")
        ).all()
    }
    company_ids_with_contacts = {
        c.company_id for c in session.exec(
            select(Contact).where(Contact.company_id != None)
        ).all()
    }
    company_ids_with_active_leads = {
        l.company_id for l in session.exec(
            select(Lead).where(Lead.status == "active", Lead.company_id != None)
        ).all()
    }
    gap_companies = session.exec(
        select(Company).where(
            Company.motivation >= 7,
            Company.is_archived == False,
        )
    ).all()

    _PILLAR_KEYWORDS = {"payment", "embed", "bank", "agenti", "ai", "identity", "fraud", "fintech", "crypto", "stablecoin"}
    _PREFERRED_STAGES = {"series_b", "series_c"}
    _OK_STAGES = {"series_a", "series_d"}

    def _gap_score(c: Company) -> float:
        score = c.lamp_score + c.motivation * 2.0
        name_lower = c.name.lower()
        intel_lower = (c.intel_summary or "").lower()
        if any(kw in name_lower or kw in intel_lower for kw in _PILLAR_KEYWORDS):
            score += 2.0
        fs = (c.funding_stage or "").lower()
        if fs in _PREFERRED_STAGES:
            score += 2.0
        elif fs in _OK_STAGES:
            score += 1.0
        if c.id in company_ids_with_active_leads:
            score += 1.0
        return score

    gap_companies_sorted = sorted(
        [c for c in gap_companies
         if c.id not in active_company_ids_with_outreach and c.id not in company_ids_with_contacts],
        key=_gap_score, reverse=True
    )
    for company in gap_companies_sorted[:3]:
        positions.append({
            "action_type": "contact_gap",
            "label": f"No contact at {company.name} — find someone to reach out to",
            "detail": f"Motivation {company.motivation} · LAMP {company.lamp_score:.0f} · no active outreach",
            "cta": "Find contacts",
            "company_id": company.id,
            "payload_id": company.id,
            "payload_type": "company",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # POSITIONS SECTION
    # ══════════════════════════════════════════════════════════════════════════

    # Monday LinkedIn import reminder
    if _now_eastern().weekday() == 0:
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

    # Prompt review nudge card
    from app.services.outreach_generator import PROMPT_VERSION
    versioned_records = session.exec(
        select(OutreachRecord).where(OutreachRecord.prompt_version == PROMPT_VERSION)
        .order_by(OutreachRecord.created_at)
    ).all()
    if versioned_records:
        first_created = versioned_records[0].created_at[:10]
        days_since_first = _days_diff(first_created, today)
        nudge_key = ("prompt_review", None)
        if nudge_key not in dismissed and (
            (len(versioned_records) >= 5 and days_since_first >= 14)
            or days_since_first >= 30
        ):
            positions.append({
                "action_type": "prompt_review",
                "label": f"Prompt review due — {len(versioned_records)} drafts sent since {PROMPT_VERSION}",
                "detail": "Check what you rewrote vs what Claude drafted.",
                "cta": "Review prompts",
                "payload_id": None,
                "payload_type": "prompt_review",
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

    # Strategy-aware sort: priority companies bubble up, urgency breaks ties within tier
    config = session.get(StrategyConfig, 1)
    priority_ids: set = set(json.loads(config.priority_company_ids)) if config else set()

    _urgency = {
        "new_reply": 50, "champion_checkin": 48, "post_meeting_followup": 45, "post_meeting_followup_2": 44, "linkedin_accepted": 40,
        "follow_up_3": 30, "follow_up_7": 20,
        "warm_path": 15, "email_escalation": 12,
        "try_linkedin_dm": 10, "email_bounce_retry": 8,
        "check_linkedin_acceptance": 5, "contact_gap": 2,
    }

    def _strategic_score(card: dict) -> int:
        score = 100 if card.get("company_id") in priority_ids else 0
        score += _urgency.get(card.get("action_type", ""), 0)
        return score

    outreach.sort(key=_strategic_score, reverse=True)

    def _not_dismissed(a):
        return (a["action_type"], a.get("payload_id")) not in dismissed

    positions = [_annotate_task(a) for a in positions if _not_dismissed(a)]
    outreach = [_annotate_task(a) for a in outreach if _not_dismissed(a)]
    events_section = [_annotate_task(a) for a in events_section if _not_dismissed(a)]

    total = len(positions) + len(outreach) + len(events_section)
    overdue = len([a for a in outreach if a["action_type"] in ("follow_up_3", "follow_up_7")])

    return {
        "date": today,
        "total_actions": total,
        "overdue_count": overdue,
        "positions": positions,
        "outreach": outreach,
        "events": events_section,
        "actions": positions + outreach + events_section,
        "priority_company_ids": list(priority_ids),
    }


_MCP_TOOL_MAP = {
    "new_reply": "get_contact_next_step",
    "post_meeting_followup": "draft_followup",
    "linkedin_accepted": "draft_linkedin_message",
    "follow_up_3": "draft_followup",
    "follow_up_7": "draft_followup",
    "check_linkedin_acceptance": "mark_linkedin_status",
    "email_escalation": "generate_outreach",
    "try_linkedin_dm": "draft_linkedin_message",
    "champion_checkin": "get_contact_next_step",
    "warm_path": "generate_outreach",
    "email_bounce_retry": "mark_email_bounced",
    "contact_gap": "find_contacts",
    "start_outreach": "generate_outreach",
    "publish_content": "schedule_linkedin_post",
    "hot_lead": "list_hot_leads",
}


def _annotate_task(task: dict) -> dict:
    tool = _MCP_TOOL_MAP.get(task.get("action_type", ""))
    if tool:
        task["mcp_tool"] = tool
    return task


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
