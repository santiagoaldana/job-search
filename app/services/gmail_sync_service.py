"""
Gmail Sync Service — daily inbox scan for sent outreach and incoming replies.

Runs once per day at 7am (folded into job_daily_morning). Looks back 24 hours.
No Claude API calls — pure string/regex matching only.

Streams handled:
  1. SENT emails → auto-create OutreachRecord if recipient matches a known Contact
  2. INBOX replies → update response_status to "positive", store ConversationMessage
  3. LinkedIn acceptance emails → update Contact.outreach_status + linkedin_accepted flag
"""

import base64
import json
import os
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    Contact, Company, OutreachRecord, ConversationMessage,
    GmailSyncState,
)

# Token stored outside OneDrive to avoid sync conflicts (same path as gmail_monitor.py)
TOKEN_DIR = Path.home() / ".job-search-gmail"

GMAIL_ACCOUNT = os.environ.get("GMAIL_ACCOUNT_1", "aldana.santiago@gmail.com")

LINKEDIN_SENDERS = {"notifications@linkedin.com", "invitations@linkedin.com"}
LINKEDIN_ACCEPT_PATTERNS = [
    r"accepted your invitation",
    r"accepted your connection",
    r"is now connected with you",
    r"you are now connected",
]

IRRELEVANT_SENDERS = [
    "noreply", "no-reply", "donotreply",
    "newsletter", "billing", "invoice", "receipt", "alerts", "updates",
]

BOUNCE_SENDERS = ["mailer-daemon", "postmaster"]
BOUNCE_SUBJECT_PATTERNS = [
    r"delivery status notification",
    r"delivery failure",
    r"undeliverable",
    r"mail delivery failed",
    r"returned mail",
    r"could not be delivered",
]

GENERIC_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "me.com", "icloud.com", "live.com"}


# ── Auth ──────────────────────────────────────────────────────────────────────

def _bootstrap_token(session: Session = None):
    """Write credentials + token to disk. Prefers DB-persisted token over env var."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    creds_b64 = os.environ.get("GMAIL_CREDENTIALS_B64", "").strip()
    if creds_b64:
        (TOKEN_DIR / "credentials.json").write_text(base64.b64decode(creds_b64).decode())

    sanitized = GMAIL_ACCOUNT.replace("@", "_").replace(".", "_")
    token_path = TOKEN_DIR / f"{sanitized}_token.json"

    # Prefer DB token (stays fresh after each sync) over static env var snapshot
    if session is not None:
        state = session.exec(
            select(GmailSyncState).where(GmailSyncState.account_email == GMAIL_ACCOUNT)
        ).first()
        if state and state.gmail_token_json:
            token_path.write_text(state.gmail_token_json)
            return

    token_b64 = os.environ.get("GMAIL_TOKEN_B64", "").strip()
    if token_b64:
        token_path.write_text(base64.b64decode(token_b64).decode())


def _persist_token(session: Session):
    """Read the current token file from disk and save it back to the DB."""
    sanitized = GMAIL_ACCOUNT.replace("@", "_").replace(".", "_")
    token_path = TOKEN_DIR / f"{sanitized}_token.json"
    if not token_path.exists():
        return
    token_json = token_path.read_text()
    state = session.exec(
        select(GmailSyncState).where(GmailSyncState.account_email == GMAIL_ACCOUNT)
    ).first()
    if not state:
        state = GmailSyncState(account_email=GMAIL_ACCOUNT)
        session.add(state)
    state.gmail_token_json = token_json
    state.updated_at = datetime.utcnow().isoformat()
    session.add(state)
    session.commit()


def _get_gmail_service(session: Session = None):
    _bootstrap_token(session)
    from skills.gmail_monitor import authenticate_gmail
    return authenticate_gmail(GMAIL_ACCOUNT)


# ── Gmail fetch helpers ───────────────────────────────────────────────────────

def _yesterday_query() -> str:
    """Gmail search date string for messages since yesterday."""
    yesterday = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y/%m/%d")
    return f"after:{yesterday}"


def _fetch_messages(service, label: str, extra_query: str = "") -> list[dict]:
    """Return list of parsed message dicts for a label in the last 24h."""
    query = _yesterday_query()
    if extra_query:
        query = f"{query} {extra_query}"
    try:
        resp = service.users().messages().list(
            userId="me",
            labelIds=[label],
            q=query,
            maxResults=50,
        ).execute()
    except Exception as e:
        print(f"[gmail_sync] list {label} error: {e}")
        return []

    messages = resp.get("messages", [])
    result = []
    for m in messages:
        parsed = _parse_message(service, m["id"])
        if parsed:
            result.append(parsed)
    return result


def _parse_message(service, msg_id: str) -> Optional[dict]:
    """Fetch and parse a single Gmail message into a flat dict."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except Exception:
        return None

    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    subject = headers.get("subject", "")
    from_raw = headers.get("from", "")
    to_raw = headers.get("to", "")
    thread_id = msg.get("threadId", "")
    internal_date = int(msg.get("internalDate", 0)) / 1000  # ms → s

    from_email, from_name = _parse_address(from_raw)
    to_email, _ = _parse_address(to_raw)
    body_text = _extract_body(msg.get("payload", {}))
    message_date = datetime.utcfromtimestamp(internal_date).isoformat() if internal_date else datetime.utcnow().isoformat()

    return {
        "gmail_message_id": msg_id,
        "thread_id": thread_id,
        "subject": subject,
        "from_email": from_email.lower(),
        "from_name": from_name,
        "to_email": to_email.lower(),
        "body_text": body_text,
        "message_date": message_date,
    }


def _parse_address(raw: str) -> tuple[str, str]:
    """Extract (email, name) from 'Name <email>' or plain 'email'."""
    m = re.match(r'"?([^"<]+)"?\s*<([^>]+)>', raw)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    raw = raw.strip().strip("<>")
    return raw, ""


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from Gmail payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


# ── Classification ────────────────────────────────────────────────────────────

def classify_email_type(from_email: str, subject: str, body_text: str) -> str:
    """Return 'linkedin_acceptance' | 'bounce' | 'outreach_reply' | 'irrelevant'."""
    from_lower = from_email.lower()
    subject_lower = subject.lower()
    body_lower = body_text.lower()[:500]

    if any(s in from_lower for s in LINKEDIN_SENDERS):
        combined = subject_lower + " " + body_lower
        if any(re.search(p, combined) for p in LINKEDIN_ACCEPT_PATTERNS):
            return "linkedin_acceptance"
        return "irrelevant"

    # Bounce detection before generic irrelevant filter
    if any(kw in from_lower for kw in BOUNCE_SENDERS):
        if any(re.search(p, subject_lower) for p in BOUNCE_SUBJECT_PATTERNS):
            return "bounce"
        # mailer-daemon is always a bounce even if subject doesn't match patterns
        return "bounce"

    if any(kw in from_lower for kw in IRRELEVANT_SENDERS):
        return "irrelevant"

    return "outreach_reply"


# ── Contact/outreach matching ─────────────────────────────────────────────────

def _add_business_days(start: date, days: int) -> date:
    """Replicates the logic from app/routers/outreach.py."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            added += 1
    return current


def match_email_to_outreach(
    session: Session,
    from_email: str,
    from_name: str,
    thread_id: str,
) -> Optional[OutreachRecord]:
    """Four-pass matching. Returns the most relevant pending OutreachRecord."""
    # Pass 1: thread continuity
    if thread_id:
        existing_msg = session.exec(
            select(ConversationMessage).where(ConversationMessage.thread_id == thread_id)
        ).first()
        if existing_msg and existing_msg.outreach_record_id:
            return session.get(OutreachRecord, existing_msg.outreach_record_id)

    # Pass 2: exact email match on Contact
    contact = session.exec(
        select(Contact).where(Contact.email == from_email)
    ).first()
    if contact:
        record = session.exec(
            select(OutreachRecord)
            .where(OutreachRecord.contact_id == contact.id)
            .where(OutreachRecord.response_status == "pending")
            .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
        ).first()
        if record:
            return record

    # Pass 3: domain match (non-generic) + name overlap
    domain = from_email.split("@")[-1] if "@" in from_email else ""
    if domain and domain not in GENERIC_DOMAINS:
        name_tokens = set(from_name.lower().split()) if from_name else set()
        contacts = session.exec(select(Contact)).all()
        for c in contacts:
            if not c.email:
                continue
            c_domain = c.email.split("@")[-1]
            if c_domain == domain:
                c_tokens = set(c.name.lower().split())
                if name_tokens & c_tokens:
                    record = session.exec(
                        select(OutreachRecord)
                        .where(OutreachRecord.contact_id == c.id)
                        .where(OutreachRecord.response_status == "pending")
                        .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
                    ).first()
                    if record:
                        return record

    # Pass 4: name token overlap >= 2
    name_tokens = set(from_name.lower().split()) if from_name else set()
    if len(name_tokens) >= 2:
        contacts = session.exec(select(Contact)).all()
        best_record, best_score = None, 0
        for c in contacts:
            c_tokens = set(c.name.lower().split())
            score = len(name_tokens & c_tokens)
            if score >= 2 and score > best_score:
                record = session.exec(
                    select(OutreachRecord)
                    .where(OutreachRecord.contact_id == c.id)
                    .where(OutreachRecord.response_status == "pending")
                    .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
                ).first()
                if record:
                    best_record, best_score = record, score
        if best_record:
            return best_record

    return None


# ── Handlers ─────────────────────────────────────────────────────────────────

def handle_linkedin_acceptance(session: Session, subject: str, body_text: str) -> dict:
    """Update Contact + OutreachRecord when LinkedIn acceptance email is detected."""
    # LinkedIn subjects use first name only: "John has accepted your invitation"
    # Try subject first (handles "John Bruce accepted" and "John has accepted")
    m = re.search(r"^(.+?)\s+(?:has\s+)?accepted your", subject, re.IGNORECASE)
    if not m:
        m = re.search(r"^(.+?)\s+(?:has\s+)?accepted your", body_text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return {"updated": False, "reason": "could not parse name from subject"}

    acceptor_name = m.group(1).strip()

    # If subject only gave a first name, try to get the full name from the body
    # LinkedIn email bodies contain the full name on its own line near the top
    if " " not in acceptor_name:
        body_name = re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*$", body_text, re.MULTILINE)
        if body_name:
            acceptor_name = body_name.group(1).strip()
    name_tokens = set(acceptor_name.lower().split())

    contacts = session.exec(select(Contact)).all()
    best_contact, best_score = None, 0
    for c in contacts:
        c_tokens = set(c.name.lower().split())
        score = len(name_tokens & c_tokens)
        if score > best_score:
            best_contact, best_score = c, score

    if not best_contact or best_score < 1:
        return {"updated": False, "reason": f"no contact matched '{acceptor_name}'"}

    best_contact.outreach_status = "connection_requested"  # already was; keep or advance
    # Mark linkedin_accepted on the most recent linkedin OutreachRecord
    record = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.contact_id == best_contact.id)
        .where(OutreachRecord.channel == "linkedin")
        .order_by(OutreachRecord.sent_at.desc())  # type: ignore[arg-type]
    ).first()

    if record:
        record.linkedin_accepted = True
        record.updated_at = datetime.utcnow().isoformat()
        session.add(record)

    session.add(best_contact)
    session.commit()

    company = session.get(Company, best_contact.company_id) if best_contact.company_id else None
    return {
        "updated": True,
        "contact_name": best_contact.name,
        "company_name": company.name if company else None,
    }


def handle_outreach_reply(session: Session, msg_data: dict, record: OutreachRecord) -> dict:
    """Store reply, flip response_status to positive, reset follow-up clock."""
    # Dedup
    existing = session.exec(
        select(ConversationMessage).where(
            ConversationMessage.gmail_message_id == msg_data["gmail_message_id"]
        )
    ).first()
    if existing:
        return {"skipped": True, "reason": "already stored"}

    today = datetime.utcnow().date()
    record.response_status = "positive"
    record.updated_at = datetime.utcnow().isoformat()
    record.follow_up_3_due = _add_business_days(today, 3).isoformat()
    record.follow_up_7_due = _add_business_days(today, 7).isoformat()
    record.follow_up_3_sent = False
    record.follow_up_7_sent = False
    session.add(record)

    if record.company_id:
        company = session.get(Company, record.company_id)
        if company and company.stage == "outreach":
            company.stage = "response"
            session.add(company)

    conv = ConversationMessage(
        outreach_record_id=record.id,
        message_date=msg_data["message_date"],
        from_email=msg_data["from_email"],
        from_name=msg_data["from_name"],
        to_email=msg_data["to_email"],
        subject=msg_data["subject"],
        body_full=msg_data["body_text"],
        message_type="reply",
        gmail_message_id=msg_data["gmail_message_id"],
        thread_id=msg_data["thread_id"],
    )
    session.add(conv)
    session.commit()

    contact = session.get(Contact, record.contact_id) if record.contact_id else None
    company = session.get(Company, record.company_id) if record.company_id else None
    return {
        "contact_name": contact.name if contact else None,
        "company_name": company.name if company else None,
        "outreach_id": record.id,
    }


def handle_bounce_email(session: Session, msg_data: dict) -> dict:
    """Extract failed address from bounce, mark contact.email_invalid=True."""
    body = msg_data["body_text"]
    subject = msg_data["subject"]

    # Extract failed recipient email from bounce body
    failed_email = None
    patterns = [
        r"(?:Final-Recipient|Original-Recipient):[^\n]*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        r"address[^\n]*?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        r"(?:couldn't be delivered to|not found|failed to deliver[^\n]*?to)\s*[:\"]?\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    ]
    for p in patterns:
        m = re.search(p, body, re.IGNORECASE)
        if m:
            failed_email = m.group(1).lower()
            break

    # Fallback: scan all email addresses in body, pick the non-gmail one
    if not failed_email:
        all_emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", body)
        for addr in all_emails:
            addr_lower = addr.lower()
            if "gmail" not in addr_lower and "google" not in addr_lower and "mailer-daemon" not in addr_lower:
                failed_email = addr_lower
                break

    if not failed_email:
        return {"bounce_handled": False, "reason": "could not extract failed email"}

    # Find contact with that email
    contact = session.exec(
        select(Contact).where(Contact.email == failed_email)
    ).first()
    if not contact:
        return {"bounce_handled": False, "reason": f"no contact with email {failed_email}", "failed_email": failed_email}

    contact.email_invalid = True
    session.add(contact)
    session.commit()

    company = session.get(Company, contact.company_id) if contact.company_id else None
    return {
        "bounce_handled": True,
        "failed_email": failed_email,
        "contact_name": contact.name,
        "company_name": company.name if company else None,
        "contact_id": contact.id,
    }


def handle_sent_email(session: Session, msg_data: dict) -> dict:
    """Auto-create OutreachRecord for sent email if recipient matches a known Contact."""
    to_email = msg_data["to_email"]
    if not to_email:
        return {"outreach_created": False, "reason": "no to_email"}

    # Match by exact email only (sent emails must match a known contact)
    contact = session.exec(
        select(Contact).where(Contact.email == to_email)
    ).first()
    if not contact:
        return {"outreach_created": False, "reason": f"no contact with email {to_email}"}

    # Dedup: already have a ConversationMessage with this gmail_message_id
    existing = session.exec(
        select(ConversationMessage).where(
            ConversationMessage.gmail_message_id == msg_data["gmail_message_id"]
        )
    ).first()
    if existing:
        return {"outreach_created": False, "reason": "already stored"}

    # Dedup: OutreachRecord for this contact sent in last 24h
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    recent = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.contact_id == contact.id)
        .where(OutreachRecord.sent_at >= cutoff)
    ).first()
    if recent:
        return {"outreach_created": False, "reason": "recent outreach record already exists"}

    today = datetime.utcnow().date()
    record = OutreachRecord(
        company_id=contact.company_id,
        contact_id=contact.id,
        channel="email",
        sent_at=msg_data["message_date"],
        subject=msg_data["subject"],
        body=msg_data["body_text"][:2000],
        response_status="pending",
        follow_up_3_due=_add_business_days(today, 3).isoformat(),
        follow_up_7_due=_add_business_days(today, 7).isoformat(),
        follow_up_3_sent=False,
        follow_up_7_sent=False,
        updated_at=datetime.utcnow().isoformat(),
    )
    session.add(record)
    session.flush()  # get record.id

    conv = ConversationMessage(
        outreach_record_id=record.id,
        message_date=msg_data["message_date"],
        from_email=msg_data["from_email"],
        from_name=msg_data["from_name"],
        to_email=msg_data["to_email"],
        subject=msg_data["subject"],
        body_full=msg_data["body_text"],
        message_type="outreach",
        gmail_message_id=msg_data["gmail_message_id"],
        thread_id=msg_data["thread_id"],
    )
    session.add(conv)

    # Advance contact status
    if contact.outreach_status in ("none", "drafted"):
        contact.outreach_status = "emailed"
        session.add(contact)

    # Advance company stage
    if contact.company_id:
        company = session.get(Company, contact.company_id)
        if company and company.stage == "pool":
            company.stage = "outreach"
            session.add(company)

    session.commit()

    company = session.get(Company, contact.company_id) if contact.company_id else None
    return {
        "outreach_created": True,
        "contact_name": contact.name,
        "company_name": company.name if company else None,
        "outreach_id": record.id,
    }


# ── State helpers ─────────────────────────────────────────────────────────────

def get_or_create_sync_state(session: Session) -> GmailSyncState:
    state = session.exec(
        select(GmailSyncState).where(GmailSyncState.account_email == GMAIL_ACCOUNT)
    ).first()
    if not state:
        state = GmailSyncState(account_email=GMAIL_ACCOUNT)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


# ── Main orchestration ────────────────────────────────────────────────────────

def run_gmail_sync(session: Session) -> dict:
    """Called once daily at 7am. Looks back 24 hours. No Claude API cost."""
    try:
        service = _get_gmail_service(session)
        _persist_token(session)  # save refreshed token back to DB immediately
    except Exception as e:
        error_msg = f"Gmail auth failed: {e}"
        try:
            state = get_or_create_sync_state(session)
            state.last_poll_at = datetime.utcnow().isoformat()
            state.last_sync_summary = json.dumps({"error": error_msg})
            state.updated_at = datetime.utcnow().isoformat()
            session.add(state)
            session.commit()
        except Exception:
            pass
        return {"error": error_msg, "new_outreach": [], "new_replies": [], "linkedin_accepted": []}

    results: dict = {"new_outreach": [], "new_replies": [], "linkedin_accepted": [], "bounces": [], "errors": []}

    # Stream 3: LinkedIn acceptance emails (INBOX from notifications@linkedin.com)
    inbox_msgs = _fetch_messages(service, "INBOX")
    for msg in inbox_msgs:
        email_type = classify_email_type(msg["from_email"], msg["subject"], msg["body_text"])

        if email_type == "linkedin_acceptance":
            r = handle_linkedin_acceptance(session, msg["subject"], msg["body_text"])
            if r.get("updated"):
                results["linkedin_accepted"].append(r)

        elif email_type == "bounce":
            r = handle_bounce_email(session, msg)
            if r.get("bounce_handled"):
                results["bounces"].append(r)
            else:
                results["errors"].append(f"bounce unhandled: {r.get('reason')} ({r.get('failed_email', '?')})")

        elif email_type == "outreach_reply":
            matched = match_email_to_outreach(session, msg["from_email"], msg["from_name"], msg["thread_id"])
            if matched:
                r = handle_outreach_reply(session, msg, matched)
                if not r.get("skipped"):
                    results["new_replies"].append(r)

    # Stream 1: Emails Santiago sent → only if recipient is a known contact
    sent_msgs = _fetch_messages(service, "SENT")
    for msg in sent_msgs:
        r = handle_sent_email(session, msg)
        if r.get("outreach_created"):
            results["new_outreach"].append(r)

    # Persist sync state
    state = get_or_create_sync_state(session)
    state.last_poll_at = datetime.utcnow().isoformat()
    state.last_sync_summary = json.dumps({
        "new_outreach": len(results["new_outreach"]),
        "new_replies": len(results["new_replies"]),
        "linkedin_accepted": len(results["linkedin_accepted"]),
        "bounces": len(results["bounces"]),
        "error": None,
    })
    state.updated_at = datetime.utcnow().isoformat()
    session.add(state)
    session.commit()

    print(f"[gmail_sync] outreach={len(results['new_outreach'])} replies={len(results['new_replies'])} li_accepted={len(results['linkedin_accepted'])} bounces={len(results['bounces'])}")
    return results
