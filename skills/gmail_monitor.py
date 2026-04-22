"""
Gmail Monitor Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Monitors aldana.santiago@gmail.com (Gmail API) and santiago@aidatasolutions.co
(Microsoft Graph API / Outlook) for job-search-related emails, matches them
against the outreach tracker, and drafts follow-up responses using the
6-point email format.

User stays in the loop: drafts are saved to data/pending_drafts.json and
reviewed via:  python3 orchestrate.py gmail review

Setup (one-time, user must do):

  Gmail account:
  1. Create Google Cloud project → Enable Gmail API → OAuth2 Desktop App credentials
  2. Download credentials JSON, place at  ~/.job-search-gmail/credentials.json
  3. Run:  python3 orchestrate.py gmail auth
  4. Add to .env:
       GMAIL_ACCOUNT_1=aldana.santiago@gmail.com

  Microsoft 365 / Outlook account (santiago@aidatasolutions.co):
  1. Register an app in Azure AD (portal.azure.com → App registrations)
     - Supported account type: "Accounts in this organizational directory only"
     - Add API permission: Microsoft Graph → Delegated → Mail.Read, Mail.Send
     - Under "Authentication" → add platform "Mobile and desktop applications"
       and enable the native client redirect URI
  2. Add to .env:
       OUTLOOK_ACCOUNT_1=santiago@aidatasolutions.co
       MS_CLIENT_ID=<your-azure-app-client-id>
       MS_TENANT_ID=<your-azure-tenant-id>   # or "common" for multi-tenant
  3. Run:  python3 orchestrate.py gmail auth
     (will trigger a device-code browser login for the Outlook account)

Architecture:
  - Polls every 30 min via launchd (StartInterval=1800)
  - Gmail: uses Gmail history API (incremental, 1-2 quota units per poll)
  - Outlook: uses Microsoft Graph /me/mailFolders/inbox/messages with
    $filter=receivedDateTime ge <last_poll> (MSAL device-code token cache)
  - State stored in data/gmail_state.json (history IDs / last poll timestamps)
  - Pending drafts in data/pending_drafts.json (user reviews before send)
  - Outlook tokens stored in ~/.job-search-gmail/<email>_ms_token.json
"""

import json
import os
import re
import base64
import email as email_lib
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt, Confirm

console = Console()

# ── Paths ─────────────────────────────────────────────────────────────────────

TOKEN_DIR = Path.home() / ".job-search-gmail"       # outside OneDrive, avoids sync conflicts
GMAIL_STATE_PATH  = None   # set after DATA_DIR import
PENDING_DRAFTS_PATH = None # set after DATA_DIR import

def _init_paths():
    global GMAIL_STATE_PATH, PENDING_DRAFTS_PATH
    from skills.shared import DATA_DIR
    GMAIL_STATE_PATH    = DATA_DIR / "gmail_state.json"
    PENDING_DRAFTS_PATH = DATA_DIR / "pending_drafts.json"
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# ── Gmail API Scopes ──────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",   # for marking read
]

# ── Job-search relevance keywords ─────────────────────────────────────────────
# Used as a first-pass filter before sending to outreach tracker matching

RELEVANT_SUBJECTS = [
    "coffee", "chat", "connect", "catch up", "follow up", "re:", "meeting",
    "call", "interview", "opportunity", "introduction", "intro", "referred",
    "your experience", "fintech", "payments", "product", "cpo", "cto",
    "svp", "vp of", "head of", "chief", "role", "position", "job",
    "linkedin", "network", "advice", "insight",
]

IRRELEVANT_SENDERS = [
    "noreply", "no-reply", "notifications", "newsletter", "donotreply",
    "mailer", "bounce", "alerts", "updates", "billing", "invoice",
    "receipt", "confirm", "verify", "unsubscribe",
]


# ── Authentication ────────────────────────────────────────────────────────────

def authenticate_gmail(account_email: str) -> object:
    """
    OAuth2 Desktop App flow. Opens browser on first run.
    Token stored in TOKEN_DIR/<sanitized_email>_token.json.
    Returns a built Gmail API service object.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. Run:\n"
            "  pip install google-api-python-client google-auth "
            "google-auth-oauthlib google-auth-httplib2"
        )

    creds_path = TOKEN_DIR / "credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials not found at {creds_path}\n"
            "  1. Create a Google Cloud project\n"
            "  2. Enable Gmail API\n"
            "  3. Create OAuth2 'Desktop app' credentials\n"
            "  4. Download the JSON and place at ~/.job-search-gmail/credentials.json"
        )

    token_file = TOKEN_DIR / f"{account_email.replace('@', '_').replace('.', '_')}_token.json"
    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


# ── Microsoft Graph / Outlook Auth ───────────────────────────────────────────

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MS_SCOPES  = ["Mail.Read", "Mail.Send", "offline_access"]


def _is_outlook_account(email: str) -> bool:
    """True for accounts that should use Microsoft Graph instead of Gmail API."""
    outlook_accounts = {
        a.strip().lower()
        for key in ["OUTLOOK_ACCOUNT_1", "OUTLOOK_ACCOUNT_2"]
        for a in [os.environ.get(key, "")]
        if a.strip()
    }
    return email.strip().lower() in outlook_accounts


def authenticate_outlook(account_email: str) -> str:
    """
    MSAL device-code flow for Microsoft 365 accounts.
    Caches the token in ~/.job-search-gmail/<email>_ms_token.json.
    Returns a valid Bearer access token string.
    """
    try:
        import msal
    except ImportError:
        raise RuntimeError(
            "MSAL not installed. Run:\n"
            "  pip install msal"
        )

    client_id = os.environ.get("MS_CLIENT_ID", "").strip()
    tenant_id  = os.environ.get("MS_TENANT_ID", "common").strip()
    if not client_id:
        raise RuntimeError(
            "MS_CLIENT_ID not set in .env\n"
            "Register an Azure app and add MS_CLIENT_ID (and MS_TENANT_ID) to .env"
        )

    token_file = TOKEN_DIR / f"{account_email.replace('@', '_').replace('.', '_')}_ms_token.json"
    authority  = f"https://login.microsoftonline.com/{tenant_id}"

    cache = msal.SerializableTokenCache()
    if token_file.exists():
        cache.deserialize(token_file.read_text())

    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)

    # Try silent refresh first
    accounts_in_cache = app.get_accounts(username=account_email)
    result = None
    if accounts_in_cache:
        result = app.acquire_token_silent(MS_SCOPES, account=accounts_in_cache[0])

    if not result or "access_token" not in result:
        # Device code flow (prints URL + code to terminal)
        flow = app.initiate_device_flow(scopes=MS_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not initiate device flow: {flow.get('error_description')}")
        console.print(f"\n[bold cyan]Outlook auth for {account_email}:[/bold cyan]")
        console.print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Outlook auth failed: {result.get('error_description', result)}")

    # Persist token cache
    if cache.has_state_changed:
        token_file.write_text(cache.serialize())

    return result["access_token"]


def fetch_new_emails_outlook(account_email: str, max_results: int = 50) -> list[dict]:
    """
    Fetch new inbox emails for a Microsoft 365 account via Microsoft Graph.
    Uses last_poll timestamp from state; falls back to 30 days ago on first run.
    Returns list of parsed email dicts (same schema as parse_email()).
    """
    import httpx

    state = _load_state()
    last_poll = state.get(account_email, {}).get("last_poll")
    if last_poll:
        since_dt = datetime.fromisoformat(last_poll)
    else:
        since_dt = datetime.now() - timedelta(days=30)

    since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        token = authenticate_outlook(account_email)
    except Exception as e:
        console.print(f"[red]Outlook auth failed for {account_email}: {e}[/red]")
        return []

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params  = {
        "$filter": f"receivedDateTime ge {since_str}",
        "$orderby": "receivedDateTime desc",
        "$top": str(max_results),
        "$select": "id,conversationId,subject,from,toRecipients,receivedDateTime,bodyPreview,body",
    }

    parsed = []
    try:
        resp = httpx.get(
            f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        messages = resp.json().get("value", [])
    except Exception as e:
        console.print(f"[red]Graph API fetch error for {account_email}: {e}[/red]")
        messages = []

    our_emails = {account_email.lower(), "aldana.santiago@gmail.com", "santiago@aidatasolutions.co"}

    for msg in messages:
        from_obj   = msg.get("from", {}).get("emailAddress", {})
        from_email = from_obj.get("address", "").lower().strip()
        from_name  = from_obj.get("name", "").strip()
        subject    = msg.get("subject", "")
        body_text  = msg.get("body", {}).get("content", "")
        # Strip HTML tags from body if HTML content type
        if msg.get("body", {}).get("contentType", "") == "html":
            body_text = re.sub(r"<[^>]+>", " ", body_text)
            body_text = re.sub(r"\s+", " ", body_text).strip()

        # Skip outbound
        if from_email in our_emails:
            continue

        # Filter spam senders
        if any(kw in from_email for kw in IRRELEVANT_SENDERS):
            continue

        # Relevance check
        subject_lower = subject.lower()
        body_lower    = body_text.lower()
        if not any(kw in subject_lower or kw in body_lower[:500] for kw in RELEVANT_SUBJECTS):
            continue

        to_recipients = msg.get("toRecipients", [])
        to_raw = ", ".join(r.get("emailAddress", {}).get("address", "") for r in to_recipients)

        parsed.append({
            "message_id":   msg.get("id", ""),
            "thread_id":    msg.get("conversationId", ""),
            "account":      account_email,
            "from_email":   from_email,
            "from_name":    from_name,
            "subject":      subject,
            "body_snippet": msg.get("bodyPreview", ""),
            "body_text":    body_text[:2000],
            "date_str":     msg.get("receivedDateTime", ""),
            "to":           to_raw,
        })

    # Update last_poll in state
    state.setdefault(account_email, {})["last_poll"] = datetime.now().isoformat()
    _save_state(state)

    return parsed


# ── State Management ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    _init_paths()
    if GMAIL_STATE_PATH.exists():
        try:
            return json.loads(GMAIL_STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    _init_paths()
    tmp = GMAIL_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, GMAIL_STATE_PATH)


# ── Email Fetching ────────────────────────────────────────────────────────────

def fetch_new_emails(service, account_email: str, max_results: int = 50) -> list[dict]:
    """
    Fetch new emails since last poll using Gmail history API.
    Falls back to timestamp-based search on first run.
    Returns list of parsed email dicts.
    """
    state = _load_state()
    account_state = state.get(account_email, {})
    history_id = account_state.get("history_id")
    last_poll  = account_state.get("last_poll")

    messages_raw = []

    if history_id:
        # Incremental: fetch history since last known historyId (1-2 quota units)
        try:
            resp = service.users().history().list(
                userId="me",
                startHistoryId=history_id,
                historyTypes=["messageAdded"],
                maxResults=max_results,
            ).execute()
            for record in resp.get("history", []):
                for msg in record.get("messagesAdded", []):
                    msg_id = msg["message"]["id"]
                    messages_raw.append(msg_id)
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "historyId" in err_str.lower():
                # History expired (>7 days gap); fall back to timestamp search
                history_id = None
                console.print(f"[yellow]History ID expired for {account_email}, falling back to timestamp search[/yellow]")
            else:
                console.print(f"[red]History list error for {account_email}: {e}[/red]")
                return []

    if not history_id:
        # Timestamp-based fallback: search messages since last_poll or 30 days ago
        if last_poll:
            since_dt = datetime.fromisoformat(last_poll)
        else:
            since_dt = datetime.now() - timedelta(days=30)
        after_epoch = int(since_dt.timestamp())
        query = f"after:{after_epoch} in:inbox"
        try:
            resp = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
            messages_raw = [m["id"] for m in resp.get("messages", [])]
        except Exception as e:
            console.print(f"[red]Message list error for {account_email}: {e}[/red]")
            return []

    if not messages_raw:
        # Still update history_id from profile
        _update_history_id(service, account_email, state)
        return []

    # Fetch full message data
    parsed = []
    for msg_id in messages_raw:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="full",
            ).execute()
            parsed_msg = parse_email(msg, account_email)
            if parsed_msg:
                parsed.append(parsed_msg)
        except Exception as e:
            console.print(f"[dim]Could not fetch message {msg_id}: {e}[/dim]")

    # Update state
    _update_history_id(service, account_email, state)
    return parsed


def _update_history_id(service, account_email: str, state: dict) -> None:
    """Refresh history ID from current profile."""
    try:
        profile = service.users().getProfile(userId="me").execute()
        new_history_id = profile.get("historyId")
        if new_history_id:
            state.setdefault(account_email, {})["history_id"] = new_history_id
        state[account_email]["last_poll"] = datetime.now().isoformat()
        _save_state(state)
    except Exception as e:
        console.print(f"[dim]Could not update history ID: {e}[/dim]")


# ── Email Parsing ─────────────────────────────────────────────────────────────

def parse_email(message: dict, account: str) -> Optional[dict]:
    """
    Extract structured fields from a Gmail API message object.
    Returns None if the message is outbound (sent by Santiago) or irrelevant.
    """
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    from_raw = headers.get("from", "")
    subject  = headers.get("subject", "")
    to_raw   = headers.get("to", "")
    date_str = headers.get("date", "")

    # Skip outbound — messages Santiago sent
    our_emails = {account, "aldana.santiago@gmail.com", "santiago@aidatasolutions.co"}
    from_lower = from_raw.lower()
    if any(e in from_lower for e in our_emails):
        return None

    # Parse from_email and from_name
    match = re.search(r"([^<]+?)\s*<([^>]+)>", from_raw)
    if match:
        from_name  = match.group(1).strip().strip('"')
        from_email = match.group(2).strip().lower()
    else:
        from_name  = ""
        from_email = from_raw.strip().lower()

    # Filter obvious spam/automated senders
    if any(kw in from_email for kw in IRRELEVANT_SENDERS):
        return None

    # Extract body text
    body_text = _extract_body(message.get("payload", {}))

    # Quick relevance check: subject must contain at least one signal word
    subject_lower = subject.lower()
    body_lower    = (body_text or "").lower()
    if not any(kw in subject_lower or kw in body_lower[:500] for kw in RELEVANT_SUBJECTS):
        return None

    return {
        "message_id":   message["id"],
        "thread_id":    message.get("threadId", ""),
        "account":      account,
        "from_email":   from_email,
        "from_name":    from_name,
        "subject":      subject,
        "body_snippet": message.get("snippet", ""),
        "body_text":    body_text,
        "date_str":     date_str,
        "to":           to_raw,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plaintext body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


# ── Contact Matching ──────────────────────────────────────────────────────────

def match_to_contact(from_email: str, from_name: str, tracker_records: list) -> Optional[dict]:
    """
    3-pass matching against outreach tracker:
      Pass 1: exact email match on contact_email field
      Pass 2: domain match (same company domain) + name partial match
      Pass 3: name token overlap (≥2 tokens matching, case-insensitive)
    Returns the matching OutreachRecord dict or None.
    """
    from_email = from_email.lower().strip()
    from_domain = from_email.split("@")[-1] if "@" in from_email else ""
    name_tokens = set(from_name.lower().split()) if from_name else set()

    # Pass 1: exact email
    for rec in tracker_records:
        if rec.get("contact_email", "").lower().strip() == from_email:
            return rec

    # Pass 2: domain + name partial
    if from_domain and from_domain not in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "me.com"}:
        for rec in tracker_records:
            rec_email = rec.get("contact_email", "").lower()
            rec_domain = rec_email.split("@")[-1] if "@" in rec_email else ""
            if rec_domain == from_domain:
                rec_name_tokens = set(rec.get("contact_name", "").lower().split())
                if name_tokens & rec_name_tokens:  # any overlap
                    return rec

    # Pass 3: name token overlap (≥2 tokens)
    if len(name_tokens) >= 2:
        for rec in tracker_records:
            rec_name_tokens = set(rec.get("contact_name", "").lower().split())
            if len(name_tokens & rec_name_tokens) >= 2:
                return rec

    return None


# ── Tracker Update ────────────────────────────────────────────────────────────

def update_tracker_on_reply(matched_record: dict, email_data: dict, all_records: list, tracker_path: Path) -> None:
    """
    Mark a contacted person as 'responded' in the tracker.
    Atomic write via temp file.
    """
    for rec in all_records:
        if (rec.get("contact_name") == matched_record.get("contact_name") and
                rec.get("company") == matched_record.get("company")):
            rec["status"] = "responded"
            rec["notes"] = (rec.get("notes", "") +
                            f"\n[Auto] Reply received {email_data['date_str']}: {email_data['body_snippet'][:120]}").strip()
            break

    tmp = tracker_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(all_records, indent=2, ensure_ascii=False))
    os.replace(tmp, tracker_path)


# ── Follow-up Candidate Identification ───────────────────────────────────────

def identify_followup_candidates(tracker_records: list, days_threshold: int = 7) -> list[tuple]:
    """
    Find contacts who:
      (a) are in 'sent' status AND
      (b) follow_up_due or second_contact_due is overdue OR
      (c) have been in 'responded' status for 30+ days without referral (harvest cycle)
    Returns list of (record, reason, days_elapsed) tuples.
    """
    today = date.today()
    candidates = []

    for rec in tracker_records:
        status = rec.get("status", "")
        if rec.get("low_priority"):
            continue

        if status == "sent":
            follow_due = rec.get("follow_up_due", "")
            second_due = rec.get("second_contact_due", "")
            sent_date  = rec.get("sent_date", "")

            if follow_due:
                try:
                    due = date.fromisoformat(follow_due)
                    if today >= due:
                        elapsed = (today - due).days
                        candidates.append((rec, "3B7 Day-3 follow-up due", elapsed))
                        continue
                except ValueError:
                    pass

            if second_due:
                try:
                    due = date.fromisoformat(second_due)
                    if today >= due:
                        elapsed = (today - due).days
                        candidates.append((rec, "3B7 Day-7 parallel contact due", elapsed))
                        continue
                except ValueError:
                    pass

        elif status == "responded":
            # Harvest cycle: check if 30+ days since last contact without referral
            last_contact = rec.get("last_contact_date") or rec.get("sent_date", "")
            if last_contact and not rec.get("referral_received"):
                try:
                    last_dt = date.fromisoformat(last_contact[:10])
                    elapsed = (today - last_dt).days
                    if elapsed >= 30:
                        candidates.append((rec, "Harvest cycle check-in due", elapsed))
                except ValueError:
                    pass

    candidates.sort(key=lambda x: -x[2])  # most overdue first
    return candidates


# ── Draft Generation ──────────────────────────────────────────────────────────

def draft_followup(record: dict, reason: str, days_elapsed: int) -> dict:
    """
    Generate a 6-point follow-up email draft using Claude Opus.
    Returns a draft dict saved to pending_drafts.json.
    """
    from skills.shared import EXECUTIVE_PROFILE, MODEL_OPUS
    import anthropic

    client = anthropic.Anthropic()

    contact_name = record.get("contact_name", "")
    company      = record.get("company", "")
    contact_role = record.get("contact_role", "")
    channel      = record.get("channel", "email")
    notes        = record.get("notes", "")

    is_harvest = "harvest" in reason.lower()
    is_day7    = "day-7" in reason.lower() or "parallel" in reason.lower()

    if is_harvest:
        context_hint = (
            f"This contact responded previously. {days_elapsed} days have passed. "
            "This is a harvest-cycle check-in: stay top-of-mind, reference something current "
            "(industry news, a company milestone, or a personal update), and gently ask "
            "if there are any opportunities to collaborate or be introduced."
        )
    elif is_day7:
        context_hint = (
            f"Day-7 follow-up: {days_elapsed} days since initial outreach with no reply. "
            "Try a different channel if possible. Keep it very short — 2 sentences max. "
            "Just checking in, no pressure."
        )
    else:
        context_hint = (
            f"Day-3 follow-up: {days_elapsed} days since initial outreach with no reply. "
            "Keep it short. Resend with one additional line of context or social proof."
        )

    prompt = f"""You are drafting a job search follow-up email for Santiago Aldana.

EXECUTIVE PROFILE:
{EXECUTIVE_PROFILE}

CONTACT DETAILS:
- Name: {contact_name}
- Role: {contact_role}
- Company: {company}
- Channel used: {channel}
- Notes from previous interactions: {notes or 'None'}

FOLLOW-UP CONTEXT:
{context_hint}

STRICT 6-POINT EMAIL RULES (Dalton method):
1. Body must be ≤75 words total — count carefully
2. Connection or affinity mentioned early
3. Ask as a question, not a statement
4. Define interest specifically (company + role type)
5. At least half the words should be about THEM, not Santiago
6. Ask for advice or insight — never ask for a job lead or referral explicitly

FORBIDDEN WORDS IN BODY: opportunity, resume, application, job search, looking for a job

Subject line format: them-focused, ambiguous ("Checking in on your work at [Company]" or "Following up on [topic from notes]")

OUTPUT FORMAT (JSON only, no markdown, no explanation):
{{
  "subject": "...",
  "body": "...",
  "word_count": <integer>,
  "reasoning": "one sentence explaining why this approach fits"
}}"""

    try:
        response = client.messages.create(
            model=MODEL_OPUS,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        draft_data = json.loads(raw)
    except Exception as e:
        draft_data = {
            "subject": f"Following up — {contact_name} at {company}",
            "body": f"Hi {contact_name.split()[0] if contact_name else 'there'},\n\nFollowing up on my earlier note. Would love to hear your perspective on [topic]. Do you have 15 minutes?\n\nBest,\nSantiago",
            "word_count": 30,
            "reasoning": f"Fallback draft (Claude error: {e})",
        }

    return {
        "draft_id":     f"{company}_{contact_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}".replace(" ", "_"),
        "company":      company,
        "contact_name": contact_name,
        "contact_email": record.get("contact_email", ""),
        "thread_id":    record.get("thread_id", ""),
        "subject":      draft_data.get("subject", ""),
        "body":         draft_data.get("body", ""),
        "word_count":   draft_data.get("word_count", 0),
        "reasoning":    draft_data.get("reasoning", ""),
        "reason":       reason,
        "days_elapsed": days_elapsed,
        "created_at":   datetime.now().isoformat(),
        "status":       "pending",   # pending | approved | skipped | sent
    }


# ── Pending Drafts Management ─────────────────────────────────────────────────

def load_pending_drafts() -> list[dict]:
    _init_paths()
    if PENDING_DRAFTS_PATH.exists():
        try:
            return json.loads(PENDING_DRAFTS_PATH.read_text())
        except Exception:
            pass
    return []


def save_pending_drafts(drafts: list[dict]) -> None:
    _init_paths()
    tmp = PENDING_DRAFTS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(drafts, indent=2, ensure_ascii=False))
    os.replace(tmp, PENDING_DRAFTS_PATH)


# ── Send via Gmail API ────────────────────────────────────────────────────────

def send_via_gmail(service, to_email: str, subject: str, body: str,
                   from_email: str, thread_id: str = "", reply_to_message_id: str = "") -> str:
    """
    Send an email via Gmail API (stays in thread if thread_id provided).
    Returns the sent message ID.
    """
    import email as email_lib
    from email.mime.text import MIMEText

    msg = MIMEText(body, "plain")
    msg["to"]      = to_email
    msg["from"]    = from_email
    msg["subject"] = subject
    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"]  = reply_to_message_id

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_payload = {"raw": raw}
    if thread_id:
        body_payload["threadId"] = thread_id

    sent = service.users().messages().send(userId="me", body=body_payload).execute()
    return sent.get("id", "")


def send_via_outlook(account_email: str, to_email: str, subject: str, body: str,
                     thread_id: str = "") -> str:
    """
    Send an email via Microsoft Graph API from an Outlook/M365 account.
    If thread_id (conversationId) is provided, replies into that thread.
    Returns the sent message ID.
    """
    import httpx

    try:
        token = authenticate_outlook(account_email)
    except Exception as e:
        raise RuntimeError(f"Outlook auth failed for {account_email}: {e}")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": "true",
    }

    # If we have a conversationId, find the latest message in that thread and reply
    if thread_id:
        try:
            search_resp = httpx.get(
                f"{GRAPH_BASE}/me/messages",
                headers=headers,
                params={
                    "$filter": f"conversationId eq '{thread_id}'",
                    "$orderby": "receivedDateTime desc",
                    "$top": "1",
                    "$select": "id",
                },
                timeout=15,
            )
            msgs = search_resp.json().get("value", [])
            if msgs:
                reply_id = msgs[0]["id"]
                reply_payload = {
                    "message": {
                        "body": {"contentType": "Text", "content": body},
                        "toRecipients": [{"emailAddress": {"address": to_email}}],
                    },
                    "comment": body,
                }
                resp = httpx.post(
                    f"{GRAPH_BASE}/me/messages/{reply_id}/reply",
                    headers=headers,
                    json=reply_payload,
                    timeout=30,
                )
                resp.raise_for_status()
                return reply_id  # Graph reply endpoint returns 202, no message ID
        except Exception:
            pass  # Fall through to sendMail if reply fails

    resp = httpx.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return "sent"  # sendMail returns 202 with no body


# ── Batch Draft Review ────────────────────────────────────────────────────────

def run_review_batch(args=None) -> None:
    """
    Batch review mode: shows N drafts as a numbered list, then lets the user
    type indices to approve (e.g. "1 3 5"), or 'a' for all, 's' to skip all.
    Much faster than one-by-one when 50+ drafts are pending.
    """
    _init_paths()
    batch_size = getattr(args, "batch", 10) or 10
    drafts = load_pending_drafts()
    pending = [d for d in drafts if d.get("status") == "pending"]

    if not pending:
        console.print(Panel("[green]No pending drafts to review.[/green]", border_style="green"))
        return

    accounts = _get_configured_accounts()
    services = {}

    total = len(pending)
    processed = 0

    while processed < total:
        batch = pending[processed: processed + batch_size]
        console.print()
        console.print(f"[bold blue]━━━ Batch {processed // batch_size + 1} — showing {len(batch)} of {total - processed} remaining ━━━[/bold blue]")
        console.print()

        # Print numbered list with one-line preview per draft
        for i, draft in enumerate(batch, 1):
            company    = draft.get("company", "")
            contact    = draft.get("contact_name", "")
            subject    = draft.get("subject", "")
            reason     = draft.get("reason", "")
            elapsed    = draft.get("days_elapsed", 0)
            wc         = draft.get("word_count", 0)
            to_email   = draft.get("contact_email", "")
            email_hint = f" <{to_email}>" if to_email else " [no email]"
            console.print(
                f"  [bold cyan]{i:>2}.[/bold cyan] "
                f"[bold]{contact}[/bold] @ {company}{email_hint}\n"
                f"      [dim]Subject:[/dim] {subject}\n"
                f"      [dim]{reason} · {elapsed}d ago · {wc}w[/dim]"
            )
            console.print()

        console.print("[dim]Enter numbers to approve+send (e.g. 1 3 5), 'a' for all, 's' to skip batch, 'q' to quit:[/dim]")
        try:
            raw = input("> ").strip().lower()
        except EOFError:
            break

        if raw == "q":
            break

        if raw == "s":
            processed += batch_size
            continue

        approve_indices: set[int] = set()
        if raw == "a":
            approve_indices = set(range(1, len(batch) + 1))
        else:
            for token in raw.split():
                try:
                    n = int(token)
                    if 1 <= n <= len(batch):
                        approve_indices.add(n)
                except ValueError:
                    pass

        # Process approvals
        for i, draft in enumerate(batch, 1):
            if i not in approve_indices:
                continue

            to_email = draft.get("contact_email", "")
            if not to_email:
                console.print(f"  [yellow]#{i} {draft.get('contact_name')} — no email address, skipping[/yellow]")
                continue

            from_account = accounts[0] if accounts else None
            if not from_account:
                console.print(f"  [red]No account configured[/red]")
                continue

            if from_account not in services and not _is_outlook_account(from_account):
                try:
                    services[from_account] = authenticate_gmail(from_account)
                except Exception as e:
                    console.print(f"  [red]Auth failed: {e}[/red]")
                    continue

            try:
                if _is_outlook_account(from_account):
                    sent_id = send_via_outlook(
                        from_account,
                        to_email=to_email,
                        subject=draft.get("subject", ""),
                        body=draft.get("body", ""),
                        thread_id=draft.get("thread_id", ""),
                    )
                else:
                    sent_id = send_via_gmail(
                        services[from_account],
                        to_email=to_email,
                        subject=draft.get("subject", ""),
                        body=draft.get("body", ""),
                        from_email=from_account,
                        thread_id=draft.get("thread_id", ""),
                    )
                # Find and update in master drafts list
                for d in drafts:
                    if d.get("draft_id") == draft.get("draft_id"):
                        d["status"] = "sent"
                        d["sent_at"] = datetime.now().isoformat()
                        break
                console.print(f"  [green]✓ Sent #{i}: {draft.get('contact_name')} @ {draft.get('company')}[/green]")
            except Exception as e:
                console.print(f"  [red]✗ Send failed #{i}: {e}[/red]")

        save_pending_drafts(drafts)
        processed += batch_size

        remaining = sum(1 for d in drafts if d.get("status") == "pending")
        if remaining == 0:
            console.print("\n[green]All drafts processed.[/green]")
            break
        console.print(f"\n[dim]{remaining} drafts remaining.[/dim]")

    console.print("\n[green]Review session complete.[/green]")


# ── Interactive Draft Review ──────────────────────────────────────────────────

def run_review(args=None) -> None:
    """
    Interactive CLI to review pending drafts.
    With --batch N: shows N drafts at once for bulk approval (faster).
    Without --batch: one-by-one review with full body display.
    """
    batch_size = getattr(args, "batch", None)
    if batch_size:
        run_review_batch(args)
        return

    _init_paths()
    drafts = load_pending_drafts()
    pending = [d for d in drafts if d.get("status") == "pending"]

    if not pending:
        console.print(Panel("[green]No pending drafts to review.[/green]", border_style="green"))
        return

    console.print(Panel(
        f"[bold]Gmail Draft Review[/bold]\n{len(pending)} draft(s) awaiting your approval\n"
        f"[dim]Tip: use --batch 10 to review 10 at a time[/dim]",
        border_style="blue"
    ))

    accounts = _get_configured_accounts()
    services = {}

    for draft in pending:
        company   = draft["company"]
        contact   = draft["contact_name"]
        to_email  = draft.get("contact_email", "")
        subject   = draft["subject"]
        body      = draft["body"]
        word_count = draft.get("word_count", 0)
        reason    = draft.get("reason", "")
        elapsed   = draft.get("days_elapsed", 0)

        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold]To:[/bold] {contact} ({company})")
        console.print(f"[bold]Email:[/bold] {to_email or '[not set]'}")
        console.print(f"[bold]Reason:[/bold] {reason} ({elapsed} days overdue)")
        console.print(f"[bold]Subject:[/bold] {subject}")
        console.print(f"\n[bold]Body[/bold] ({word_count} words):\n")
        console.print(body)
        console.print()

        action = Prompt.ask(
            "[bold yellow]Action[/bold yellow]",
            choices=["a", "e", "s", "d"],
            default="s",
            show_choices=True,
            show_default=True,
        )
        # a=approve+send, e=edit, s=skip, d=delete

        if action == "d":
            draft["status"] = "deleted"
            console.print("[dim]Draft deleted.[/dim]")
            continue

        if action == "s":
            console.print("[dim]Skipped.[/dim]")
            continue

        if action == "e":
            console.print("[yellow]Paste the updated body (end with a blank line):[/yellow]")
            lines = []
            while True:
                try:
                    line = input()
                    if line == "":
                        break
                    lines.append(line)
                except EOFError:
                    break
            body = "\n".join(lines)
            draft["body"]       = body
            draft["word_count"] = len(body.split())
            new_subject = Prompt.ask("Subject line", default=subject)
            draft["subject"] = new_subject
            subject = new_subject
            action = "a"  # fall through to send

        if action == "a":
            if not to_email:
                to_email = Prompt.ask("Contact email address").strip()
                draft["contact_email"] = to_email

            if not to_email:
                console.print("[red]No email address — cannot send. Skipping.[/red]")
                continue

            # Pick which account to send from
            from_account = accounts[0] if accounts else "aldana.santiago@gmail.com"
            if len(accounts) > 1:
                from_account = Prompt.ask("Send from which account", choices=accounts, default=accounts[0])

            # Auth (Gmail only; Outlook auth is handled inside send_via_outlook)
            if not _is_outlook_account(from_account) and from_account not in services:
                try:
                    services[from_account] = authenticate_gmail(from_account)
                except Exception as e:
                    console.print(f"[red]Auth failed for {from_account}: {e}[/red]")
                    continue

            try:
                if _is_outlook_account(from_account):
                    sent_id = send_via_outlook(
                        from_account,
                        to_email=to_email,
                        subject=subject,
                        body=body,
                        thread_id=draft.get("thread_id", ""),
                    )
                else:
                    sent_id = send_via_gmail(
                        services[from_account],
                        to_email=to_email,
                        subject=subject,
                        body=body,
                        from_email=from_account,
                        thread_id=draft.get("thread_id", ""),
                    )
                draft["status"] = "sent"
                draft["sent_at"] = datetime.now().isoformat()
                console.print(f"[green]Sent! Message ID: {sent_id}[/green]")
            except Exception as e:
                console.print(f"[red]Send failed: {e}[/red]")

    save_pending_drafts(drafts)
    console.print("\n[green]Review complete.[/green]")


# ── Status Display ─────────────────────────────────────────────────────────────

def run_status_gmail(args=None) -> None:
    """Show Gmail monitor status: last poll times, pending drafts, accounts."""
    _init_paths()
    state  = _load_state()
    drafts = load_pending_drafts()
    accounts = _get_configured_accounts()

    table = Table(title="Email Monitor Status", box=box.ROUNDED)
    table.add_column("Account")
    table.add_column("Type")
    table.add_column("Last Poll")
    table.add_column("Token")

    for acct in accounts:
        acct_state = state.get(acct, {})
        last_poll  = acct_state.get("last_poll", "—")
        if _is_outlook_account(acct):
            acct_type  = "Outlook/M365"
            token_file = TOKEN_DIR / f"{acct.replace('@', '_').replace('.', '_')}_ms_token.json"
        else:
            acct_type  = "Gmail"
            token_file = TOKEN_DIR / f"{acct.replace('@', '_').replace('.', '_')}_token.json"
        token_status = "[green]✓[/green]" if token_file.exists() else "[red]Not authorized[/red]"
        table.add_row(acct, acct_type, last_poll[:16] if last_poll != "—" else "—", token_status)

    console.print(table)

    pending_count = sum(1 for d in drafts if d.get("status") == "pending")
    console.print(f"\n[bold]Pending drafts:[/bold] {pending_count}")
    if pending_count:
        console.print("  Run: [cyan]python3 orchestrate.py gmail review[/cyan]")


# ── Main Monitor Cycle ────────────────────────────────────────────────────────

def run_monitor_cycle(args=None) -> str:
    """
    Full monitoring cycle (runs every 30 min via launchd):
      1. For each configured account: authenticate + fetch new emails
      2. Match each email to outreach tracker contacts
      3. Update tracker status for matched replies
      4. Identify follow-up candidates from tracker (3B7 + harvest)
      5. Generate draft follow-ups for candidates
      6. Save to pending_drafts.json (user reviews via 'gmail review')
    """
    _init_paths()
    from skills.shared import DATA_DIR

    accounts = _get_configured_accounts()
    if not accounts:
        return "No accounts configured. Add GMAIL_ACCOUNT_1 or OUTLOOK_ACCOUNT_1 to .env"

    # Load outreach tracker
    tracker_path = DATA_DIR / "outreach_tracker.json"
    if not tracker_path.exists():
        return "Outreach tracker not found. Run: python3 orchestrate.py outreach --status"
    tracker_records = json.loads(tracker_path.read_text())

    new_replies = []
    errors = []

    for account in accounts:
        try:
            if _is_outlook_account(account):
                emails = fetch_new_emails_outlook(account)
            else:
                service = authenticate_gmail(account)
                emails  = fetch_new_emails(service, account)
            console.print(f"[dim]{account}: {len(emails)} new relevant email(s)[/dim]")

            for email_data in emails:
                matched = match_to_contact(
                    email_data["from_email"],
                    email_data["from_name"],
                    tracker_records,
                )
                if matched:
                    update_tracker_on_reply(matched, email_data, tracker_records, tracker_path)
                    new_replies.append((matched, email_data))
                    console.print(
                        f"[green]Reply matched: {matched.get('contact_name')} "
                        f"@ {matched.get('company')} → status updated to 'responded'[/green]"
                    )
        except Exception as e:
            errors.append(f"{account}: {e}")
            console.print(f"[red]Error monitoring {account}: {e}[/red]")

    # Identify follow-up candidates
    candidates = identify_followup_candidates(tracker_records)
    console.print(f"[dim]Follow-up candidates: {len(candidates)}[/dim]")

    # Generate drafts (only if API key available)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    drafts  = load_pending_drafts()
    # Track already-pending companies+contacts to avoid duplicates
    already_pending = {
        (d["company"], d["contact_name"])
        for d in drafts
        if d.get("status") == "pending"
    }

    new_draft_count = 0
    for record, reason, days_elapsed in candidates:
        key = (record.get("company", ""), record.get("contact_name", ""))
        if key in already_pending:
            continue
        if api_key:
            try:
                draft = draft_followup(record, reason, days_elapsed)
                drafts.append(draft)
                already_pending.add(key)
                new_draft_count += 1
                console.print(f"[dim]Draft created for {key[1]} @ {key[0]}[/dim]")
            except Exception as e:
                console.print(f"[yellow]Draft generation failed for {key}: {e}[/yellow]")
        else:
            # No API key — create a placeholder draft without Claude
            placeholder = {
                "draft_id":     f"{key[0]}_{key[1]}_{datetime.now().strftime('%Y%m%d%H%M%S')}".replace(" ", "_"),
                "company":      key[0],
                "contact_name": key[1],
                "contact_email": record.get("contact_email", ""),
                "thread_id":    "",
                "subject":      f"Following up — {key[1]} at {key[0]}",
                "body":         "[Draft not generated — no ANTHROPIC_API_KEY. Edit before sending.]",
                "word_count":   0,
                "reasoning":    "No API key available",
                "reason":       reason,
                "days_elapsed": days_elapsed,
                "created_at":   datetime.now().isoformat(),
                "status":       "pending",
            }
            drafts.append(placeholder)
            already_pending.add(key)
            new_draft_count += 1

    save_pending_drafts(drafts)

    summary_parts = [
        f"Accounts checked: {len(accounts) - len(errors)}/{len(accounts)}",
        f"New replies matched: {len(new_replies)}",
        f"New drafts created: {new_draft_count}",
    ]
    if errors:
        summary_parts.append(f"Errors: {'; '.join(errors)}")

    return " | ".join(summary_parts)


# ── Auth subcommand ───────────────────────────────────────────────────────────

def run_auth(args=None) -> None:
    """Authenticate all configured accounts (Gmail OAuth browser flow; Outlook device-code flow)."""
    accounts = _get_configured_accounts()
    if not accounts:
        console.print("[red]No accounts configured. Add GMAIL_ACCOUNT_1 or OUTLOOK_ACCOUNT_1 to .env[/red]")
        return

    for acct in accounts:
        console.print(f"\nAuthenticating [cyan]{acct}[/cyan] ...")
        try:
            if _is_outlook_account(acct):
                authenticate_outlook(acct)
            else:
                authenticate_gmail(acct)
            console.print(f"[green]✓ {acct} authenticated[/green]")
        except Exception as e:
            console.print(f"[red]✗ {acct} failed: {e}[/red]")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_configured_accounts() -> list[str]:
    """Return all configured accounts (Gmail + Outlook), in order."""
    accounts = []
    for key in ["GMAIL_ACCOUNT_1", "GMAIL_ACCOUNT_2", "OUTLOOK_ACCOUNT_1", "OUTLOOK_ACCOUNT_2"]:
        val = os.environ.get(key, "").strip()
        if val and val not in accounts:
            accounts.append(val)
    return accounts
