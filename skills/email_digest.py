"""
Email Digest Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Reads the events cache, renders a color-coded HTML email, and sends it
via iCloud SMTP. Password is retrieved from macOS Keychain — never stored
in any file.

Usage:
  python3 -m skills.email_digest          # Preview HTML in browser (no send)
  python3 orchestrate.py digest           # Run event discovery + send email
"""

import json
import smtplib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from sqlmodel import Session

from skills.shared import DATA_DIR
from app.database import engine
from app.models import OutreachRecord, Contact, Company

# ── Config ────────────────────────────────────────────────────────────────────

EMAIL_ADDRESS = "santiago.aldana@me.com"
SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587
KEYCHAIN_SERVICE = "job-search-mailer"

CATEGORY_COLORS = {
    "STRATEGIC":        "#0057b7",  # blue
    "HIGH_PROBABILITY": "#2d8a4e",  # green
    "WILDCARD":         "#e07b00",  # orange
}

CATEGORY_LABELS = {
    "STRATEGIC":        "Strategic",
    "HIGH_PROBABILITY": "High Probability",
    "WILDCARD":         "Wildcard",
}

# ── Keychain ──────────────────────────────────────────────────────────────────

def get_icloud_password() -> "str | None":
    """
    Retrieve iCloud App Password from macOS Keychain via `security` CLI.
    Returns password string or None on failure.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-a", EMAIL_ADDRESS,
             "-s", KEYCHAIN_SERVICE,
             "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"[Email Digest] Keychain lookup failed: {result.stderr.strip()}", file=sys.stderr)
        print("[Email Digest] Run: security add-generic-password "
              f"-a {EMAIL_ADDRESS} -s {KEYCHAIN_SERVICE} -w", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[Email Digest] Keychain error: {e}", file=sys.stderr)
        return None


# ── Event Loading ─────────────────────────────────────────────────────────────

def load_events(cache_path: Path, days_ahead: int = 60) -> list[dict]:
    """
    Read events_cache.json. Filter to events with a parseable date within
    `days_ahead` days from today. Sort ascending by date.
    Events with date == "recurring" or unparseable dates are silently excluded.
    Returns [] if cache is missing or empty.
    """
    if not cache_path.exists():
        return []

    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Email Digest] Could not read cache: {e}", file=sys.stderr)
        return []

    today = datetime.now(tz=timezone.utc).date()
    cutoff = today + timedelta(days=days_ahead)
    results = []

    for event in raw:
        date_str = event.get("date", "")
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue  # Skip "recurring" and other non-parseable dates

        if today <= event_date <= cutoff:
            event["_date_obj"] = event_date
            results.append(event)

    results.sort(key=lambda e: e["_date_obj"])
    return results


def is_cache_stale(cache_path: Path, threshold_days: int = 7) -> bool:
    """Return True if cache file is older than threshold_days or missing."""
    if not cache_path.exists():
        return True
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(tz=timezone.utc) - mtime).days >= threshold_days


# ── Event Grouping ────────────────────────────────────────────────────────────

def group_events(events: list[dict]) -> dict[str, list[dict]]:
    """
    Bucket events into three temporal groups based on days from today.
      THIS_WEEK  — within next 7 days
      THIS_MONTH — 8 to 30 days out
      UPCOMING   — 31 to 60 days out
    """
    today = datetime.now(tz=timezone.utc).date()
    groups: dict[str, list[dict]] = {"THIS_WEEK": [], "THIS_MONTH": [], "UPCOMING": []}

    for event in events:
        delta = (event["_date_obj"] - today).days
        if delta <= 7:
            groups["THIS_WEEK"].append(event)
        elif delta <= 30:
            groups["THIS_MONTH"].append(event)
        else:
            groups["UPCOMING"].append(event)

    return groups


def is_urgent(event: dict, threshold_days: int = 7) -> bool:
    """True if event is within threshold_days from today."""
    today = datetime.now(tz=timezone.utc).date()
    return (event["_date_obj"] - today).days <= threshold_days


# ── HTML Rendering ────────────────────────────────────────────────────────────

def _render_event_card(event: dict) -> str:
    category = event.get("category", "WILDCARD")
    color = CATEGORY_COLORS.get(category, "#888888")
    label = CATEGORY_LABELS.get(category, category.title())
    urgent = is_urgent(event)

    urgent_badge = (
        '<span style="background:#cc0000;color:#fff;font-size:11px;'
        'padding:2px 8px;border-radius:3px;float:right;font-weight:600;">'
        '⚡ Register Soon</span>'
    ) if urgent else ""

    name = event.get("name", "Unnamed Event")
    date_str = event.get("date", "")
    location = event.get("location", "")
    cost = event.get("cost", "")
    net_score = event.get("net_score", "")
    url = event.get("url", "#")

    # Format date nicely
    try:
        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")
    except ValueError:
        date_display = date_str

    meta_parts = [p for p in [date_display, location, cost] if p]
    meta_line = " &nbsp;·&nbsp; ".join(meta_parts)

    return f"""
<div style="border-left:4px solid {color};padding:12px 16px;margin:10px 0;
            background:#fafafa;border-radius:0 6px 6px 0;overflow:hidden;">
  {urgent_badge}
  <div style="font-weight:600;font-size:15px;color:#1a1a2e;margin-bottom:4px;">
    {name}
  </div>
  <div style="font-size:12px;color:#666;margin-bottom:6px;">
    {meta_line}
  </div>
  <div style="font-size:13px;">
    <span style="color:{color};font-weight:600;font-size:11px;
                 text-transform:uppercase;letter-spacing:0.5px;">{label}</span>
    &nbsp;·&nbsp;
    <span style="color:#888;font-size:12px;">Score: {net_score}</span>
    &nbsp;·&nbsp;
    <a href="{url}" style="color:#0057b7;text-decoration:none;font-size:12px;">
      View &amp; Register →
    </a>
  </div>
</div>"""


def get_recent_replies(hours: int = 24) -> list[dict]:
    """
    Fetch outreach records that received replies in the last N hours.
    Returns list of dicts: [{contact_name, company_name, sent_date, days_elapsed, notes_snippet}]
    """
    try:
        with Session(engine) as session:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            records = session.query(OutreachRecord).filter(
                OutreachRecord.response_status == "pending",
                OutreachRecord.updated_at >= cutoff_time.isoformat(),
            ).order_by(OutreachRecord.updated_at.desc()).all()

            replies = []
            for rec in records:
                # Check notes for [Auto] reply indication
                if "[Auto] Reply" not in (rec.notes or ""):
                    continue

                company = session.get(Company, rec.company_id) if rec.company_id else None
                contact = session.get(Contact, rec.contact_id) if rec.contact_id else None

                # Calculate days since sent
                days_elapsed = 0
                if rec.sent_at:
                    try:
                        sent_date = datetime.fromisoformat(rec.sent_at[:10]).date()
                        days_elapsed = (datetime.utcnow().date() - sent_date).days
                    except (ValueError, TypeError):
                        pass

                # Extract reply snippet from notes
                notes_snippet = ""
                if rec.notes and "[Auto] Reply" in rec.notes:
                    lines = rec.notes.split("\n")
                    for i, line in enumerate(lines):
                        if "[Auto] Reply" in line:
                            notes_snippet = line[:150]  # 150 char snippet
                            break

                replies.append({
                    "contact_name": contact.name if contact else "Unknown",
                    "company_name": company.name if company else "Unknown",
                    "sent_date": rec.sent_at[:10] if rec.sent_at else "Unknown",
                    "days_elapsed": days_elapsed,
                    "notes_snippet": notes_snippet,
                    "outreach_id": rec.id,
                })

            return replies
    except Exception as e:
        print(f"[Email Digest] Warning: Could not fetch recent replies: {e}", file=sys.stderr)
        return []


def _render_section(title: str, events: list[dict], icon: str = "") -> str:
    if not events:
        return ""

    cards = "".join(_render_event_card(e) for e in events)
    return f"""
<div style="padding:16px 32px 8px;">
  <h2 style="font-size:12px;text-transform:uppercase;letter-spacing:1px;
             color:#555;border-bottom:2px solid #eee;padding-bottom:8px;
             margin:0 0 4px;">{icon} {title}</h2>
  {cards}
</div>"""


def render_html(grouped: dict[str, list[dict]], date_range_label: str, recent_replies: list[dict] = None) -> str:
    """
    Render the full HTML email from grouped events and recent replies.
    All CSS is inline — required for email client compatibility.
    max-width: 600px for mobile readability.
    """
    if recent_replies is None:
        recent_replies = []

    now_str = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    total = sum(len(v) for v in grouped.values())

    # Build replies section
    replies_content = ""
    if recent_replies:
        replies_content = '<div style="padding:20px 32px;border-bottom:1px solid #eee;">'
        replies_content += '<h2 style="margin:0 0 16px;font-size:16px;font-weight:600;color:#0d6a1c;">🔔 Replies Received</h2>'
        for reply in recent_replies[:10]:  # Limit to 10 most recent
            contact = reply.get("contact_name", "Unknown")
            company = reply.get("company_name", "Unknown")
            days = reply.get("days_elapsed", 0)
            snippet = reply.get("notes_snippet", "")

            replies_content += f'''
<div style="padding:12px 0;border-bottom:1px solid #f0f0f0;font-size:13px;">
  <div style="margin:0;color:#333;">
    <strong>{contact}</strong> @ {company}
  </div>
  <div style="margin:4px 0 0;color:#666;font-size:12px;">
    Replied {days} day{"s" if days != 1 else ""} after initial outreach
  </div>
  <div style="margin:4px 0 0;color:#888;font-size:11px;font-style:italic;">
    {snippet[:100]}...
  </div>
  <div style="margin:8px 0 0;">
    <a href="mailto:" style="color:#0057b7;text-decoration:none;font-size:12px;">
      → View conversation & draft Day-3 follow-up
    </a>
  </div>
</div>'''

        replies_content += '</div>'

    # Empty state
    if total == 0 and not recent_replies:
        body_content = """
<div style="padding:40px 32px;text-align:center;color:#888;">
  <div style="font-size:32px;margin-bottom:12px;">📭</div>
  <p style="font-size:15px;margin:0 0 8px;">No upcoming events found in the next 60 days.</p>
  <p style="font-size:13px;color:#aaa;">
    Run <code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;">
    python3 orchestrate.py events</code> to refresh the event cache.
  </p>
</div>"""
    else:
        this_week = _render_section("This Week", grouped["THIS_WEEK"], "🔥")
        this_month = _render_section("This Month", grouped["THIS_MONTH"], "📅")
        upcoming = _render_section("Upcoming", grouped["UPCOMING"], "🗓")
        body_content = replies_content + this_week + this_month + upcoming

    # Legend
    legend_items = "".join(
        f'<span style="margin-right:16px;font-size:12px;">'
        f'<span style="display:inline-block;width:10px;height:10px;'
        f'background:{color};border-radius:2px;margin-right:4px;vertical-align:middle;"></span>'
        f'{label}</span>'
        for category, color in CATEGORY_COLORS.items()
        for lbl, cat in [(CATEGORY_LABELS.get(category, ""), category)]
        if cat == category
        for label in [CATEGORY_LABELS.get(category, "")]
    )

    stale_warning = ""
    cache_path = DATA_DIR / "events_cache.json"
    if is_cache_stale(cache_path):
        stale_warning = """
<div style="background:#fff3cd;border:1px solid #ffc107;padding:10px 32px;
            font-size:12px;color:#856404;">
  ⚠️ Event data may be stale. Cache is older than 7 days.
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Your Week in Events — {date_range_label}</title>
</head>
<body style="margin:0;padding:20px;background:#f0f0f5;
             font-family:-apple-system,Arial,Helvetica,sans-serif;">

<div style="max-width:600px;margin:0 auto;background:#ffffff;
            border-radius:8px;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- HEADER -->
  <div style="background:#1a1a2e;color:#ffffff;padding:24px 32px;">
    <h1 style="margin:0;font-size:20px;font-weight:700;">
      📅 Your Week in Events
    </h1>
    <p style="margin:6px 0 0;color:#8888aa;font-size:13px;">
      {date_range_label} &nbsp;·&nbsp; {total} event{"s" if total != 1 else ""} &nbsp;·&nbsp; Generated {now_str}
    </p>
  </div>

  {stale_warning}

  <!-- LEGEND -->
  <div style="padding:10px 32px;background:#f8f8fc;border-bottom:1px solid #eee;">
    <span style="color:#888;font-size:11px;text-transform:uppercase;
                 letter-spacing:0.5px;margin-right:12px;">Category:</span>
    <span style="font-size:12px;">
      <span style="display:inline-block;width:10px;height:10px;
             background:#0057b7;border-radius:2px;margin-right:4px;vertical-align:middle;"></span>Strategic
      &nbsp;&nbsp;
      <span style="display:inline-block;width:10px;height:10px;
             background:#2d8a4e;border-radius:2px;margin-right:4px;vertical-align:middle;"></span>High Probability
      &nbsp;&nbsp;
      <span style="display:inline-block;width:10px;height:10px;
             background:#e07b00;border-radius:2px;margin-right:4px;vertical-align:middle;"></span>Wildcard
    </span>
  </div>

  <!-- EVENT SECTIONS -->
  {body_content}

  <!-- FOOTER -->
  <div style="padding:20px 32px;background:#f8f8fc;border-top:1px solid #eee;
              font-size:11px;color:#aaa;text-align:center;">
    <p style="margin:0 0 4px;">
      Job Search Orchestration System &nbsp;·&nbsp; Santiago Aldana
    </p>
    <p style="margin:0;color:#ccc;">
      Scoring: Net = Utility − (Risk × 0.4) &nbsp;·&nbsp;
      Add events: <code>python3 orchestrate.py events --add-url "URL"</code>
    </p>
  </div>

</div>
</body>
</html>"""


# ── Email Sending ─────────────────────────────────────────────────────────────

def send_email(
    html_body: str,
    subject: str,
    from_addr: str = EMAIL_ADDRESS,
    to_addr: str = EMAIL_ADDRESS,
    smtp_host: str = SMTP_HOST,
    smtp_port: int = SMTP_PORT,
) -> None:
    """
    Send HTML email via iCloud SMTP with STARTTLS.
    Password retrieved from macOS Keychain.
    Raises RuntimeError if password unavailable.
    Raises smtplib.SMTPException on send failure.
    """
    password = get_icloud_password()
    if not password:
        raise RuntimeError(
            "iCloud App Password not found in Keychain. "
            f"Run: security add-generic-password -a {from_addr} -s {KEYCHAIN_SERVICE} -w"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(from_addr, password)
        server.send_message(msg)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run() -> str:
    """
    Main entry point called by orchestrate.py digest command.
    Loads events → groups → fetches recent replies → renders → sends.
    Returns status string. Does not raise — all errors are caught and reported.
    """
    cache_path = DATA_DIR / "events_cache.json"

    # 1. Load events
    events = load_events(cache_path)

    # 2. Fetch recent replies
    recent_replies = get_recent_replies(hours=24)

    if not events and not recent_replies:
        msg = "[Email Digest] No upcoming events or recent replies found."
        print(msg)
        return msg

    # 3. Group events
    grouped = group_events(events) if events else {"THIS_WEEK": [], "THIS_MONTH": [], "UPCOMING": []}

    # 4. Build date range label for subject + header
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    date_range = f"{monday.strftime('%b %-d')} – {sunday.strftime('%b %-d, %Y')}"
    subject = f"📅 Your Week in Events — {date_range}"

    # 5. Render HTML
    html = render_html(grouped, date_range, recent_replies=recent_replies)

    # 6. Send
    try:
        send_email(html, subject)
        event_count = sum(len(v) for v in grouped.values())
        reply_count = len(recent_replies)
        result = f"Email digest sent to {EMAIL_ADDRESS} — {event_count} events, {reply_count} recent replies"
        print(f"[Email Digest] {result}")
        return result
    except RuntimeError as e:
        msg = f"[Email Digest] Keychain error: {e}"
        print(msg, file=sys.stderr)
        return msg
    except smtplib.SMTPException as e:
        msg = f"[Email Digest] SMTP error: {e}"
        print(msg, file=sys.stderr)
        return msg
    except Exception as e:
        msg = f"[Email Digest] Unexpected error: {e}"
        print(msg, file=sys.stderr)
        return msg


# ── CLI / Preview Mode ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess as _sp

    cache_path = DATA_DIR / "events_cache.json"
    events = load_events(cache_path)
    grouped = group_events(events) if events else {"THIS_WEEK": [], "THIS_MONTH": [], "UPCOMING": []}
    recent_replies = get_recent_replies(hours=24)

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    date_range = f"{monday.strftime('%b %-d')} – {sunday.strftime('%b %-d, %Y')}"

    html = render_html(grouped, date_range, recent_replies=recent_replies)

    preview_path = DATA_DIR / "digest_preview.html"
    preview_path.write_text(html, encoding="utf-8")
    print(f"[Email Digest] Preview written to {preview_path}")
    print(f"[Email Digest] Events loaded: {len(events)}")
    for group, evs in grouped.items():
        print(f"  {group}: {len(evs)}")
    print(f"[Email Digest] Recent replies: {len(recent_replies)}")

    # Open in default browser for visual inspection
    _sp.run(["open", str(preview_path)])
    print("[Email Digest] Opened in browser. Run 'python3 orchestrate.py digest' to send.")
