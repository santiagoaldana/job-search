"""
Outreach Tracker Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Implements the full 2-Hour Job Search (Steve Dalton) outreach cycle:

  1. 6-Point Email Generation — ≤75 words, favor-ask framing, them-focused subject
  2. 3B7 Follow-up Scheduling — Day 3: contact #2 in parallel; Day 7: same email, different channel
  3. TIARA Informational Meeting Prep — Trends/Insights/Advice/Resources/Assignments
  4. Harvest Cycle Tracking — monthly check-ins, booster vs obligate classification

The 6-point email rules (Dalton):
  1. ≤75 words in body
  2. Connection/affinity early
  3. Ask as question (not statement)
  4. Define interest specifically
  5. At least half the words about THEM
  6. Ask for advice/insight, not job leads

Usage:
  python3 orchestrate.py outreach --company Stripe --contact "Jane Smith" --role "CPO"
  python3 orchestrate.py outreach --tiara --company Stripe --contact "Jane Smith" --role "CPO"
  python3 orchestrate.py outreach --track --company Stripe --contact "Jane Smith" --channel email
  python3 orchestrate.py outreach --status
  python3 orchestrate.py outreach --mark-responded "Stripe:Jane Smith" --booster
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from sqlmodel import Session

from skills.shared import DATA_DIR, EXECUTIVE_PROFILE, MODEL_OPUS
from app.database import engine
from app.models import ConversationMessage, OutreachRecord as DBOutreachRecord

console = Console()

TRACKER_CACHE  = DATA_DIR / "outreach_tracker.json"
TRACKER_REPORT = DATA_DIR / "outreach_report.md"

CHANNELS = {"linkedin_group", "email", "linkedin_connect"}
VALID_STATUSES = {"sent", "responded", "booster", "obligate", "no_response", "closed"}


# ── Business Day Math ─────────────────────────────────────────────────────────

def _add_business_days(start: date, days: int) -> date:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            added += 1
    return d


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class OutreachRecord:
    company: str
    contact_name: str
    contact_role: str
    contact_email: str = ""
    channel: str = "email"               # linkedin_group | email | linkedin_connect
    sent_date: str = ""                  # ISO date YYYY-MM-DD
    status: str = "sent"
    follow_up_due: str = ""              # sent_date + 3 business days
    second_contact_due: str = ""         # sent_date + 7 business days (follow up same email diff channel)
    second_contact_name: str = ""        # parallel contact to try on day 3
    notes: str = ""
    informational_done: bool = False
    referral_received: bool = False
    referral_contact: str = ""
    generated_email: str = ""            # cached generated email body
    generated_subject: str = ""


# ── Persistence ───────────────────────────────────────────────────────────────

def load_tracker(path: Path = TRACKER_CACHE) -> list[OutreachRecord]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [OutreachRecord(**r) for r in raw]
    except Exception:
        return []


def save_tracker(records: list[OutreachRecord], path: Path = TRACKER_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _find_record(records: list[OutreachRecord], company: str, contact: str) -> Optional[OutreachRecord]:
    co_norm  = company.strip().lower()
    ct_norm  = contact.strip().lower()
    for r in records:
        if r.company.lower() == co_norm and r.contact_name.lower() == ct_norm:
            return r
    return None


# ── 6-Point Email Generation ─────────────────────────────────────────────────

_SIX_POINT_PROMPT = """You are writing a short outreach email on behalf of Santiago Aldana to {contact_name}, who is {contact_role} at {company}.

Santiago's background (draw ONLY from this — do not invent credentials):
{profile}

{bridge_section}

Write a 6-point outreach email following Steve Dalton's 2-Hour Job Search method EXACTLY:

RULES (non-negotiable):
1. Body must be ≤75 words. Count carefully.
2. Open with the connection/affinity (MIT Sloan network, FinTech community, payments ecosystem, Boston, etc.)
3. The main ask must be phrased as a QUESTION, not a statement
4. Define Santiago's interest SPECIFICALLY (mention {company} and a relevant domain)
5. At least HALF the words must be about {contact_name} or their work — not about Santiago
6. Ask for ADVICE and INSIGHT — never ask for job leads, referrals, or to "learn about openings"
7. FORBIDDEN words/phrases: "opportunity", "resume", "application", "job search", "looking for a role", "excited to share", "hope this finds you well", "I'm reaching out because"

Subject line format: "Your [specific role/domain] experience at {company}" — curiosity-inducing, ambiguous sender (could be recruiter)

{role_context}

Output format (JSON only, no markdown):
{{
  "subject": "...",
  "body": "...",
  "word_count": <integer>,
  "connection_used": "what affinity/connection was referenced"
}}"""


def generate_six_point_email(
    contact_name: str,
    contact_role: str,
    company: str,
    role_context: str = "",
    bridge_contact: str = "",
) -> dict:
    """
    Generate a 6-point outreach email via Claude Opus.
    Returns dict with subject, body, word_count, connection_used.
    """
    bridge_section = ""
    if bridge_contact:
        bridge_section = f"Bridge contact: Santiago has a mutual connection — {bridge_contact} — who works at or is connected to {company}. Reference this naturally."

    prompt = _SIX_POINT_PROMPT.format(
        contact_name   = contact_name,
        contact_role   = contact_role,
        company        = company,
        profile        = EXECUTIVE_PROFILE,
        bridge_section = bridge_section,
        role_context   = f"Additional context about what Santiago is exploring: {role_context}" if role_context else "",
    )

    client  = anthropic.Anthropic()
    message = client.messages.create(
        model      = MODEL_OPUS,
        max_tokens = 600,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract manually
        result = {"subject": "", "body": raw, "word_count": len(raw.split()), "connection_used": ""}

    return result


# ── TIARA Prep Generation ─────────────────────────────────────────────────────

_TIARA_PROMPT = """You are preparing Santiago Aldana for an informational meeting with {contact_name}, who is {contact_role} at {company}.

Santiago's background:
{profile}

{role_context}

Generate a TIARA framework prep sheet for this meeting. TIARA = Trends, Insights, Advice, Resources, Assignments.

The goal: Turn a stranger into an advocate in 30 minutes. DO NOT sell Santiago. Make {contact_name} feel like the expert and hero.

Output exactly this structure (JSON, no markdown):
{{
  "small_talk": [
    "opener 1 — reference something specific about their role or tenure at {company}",
    "opener 2 — industry adjacent, easy to respond to"
  ],
  "trends": [
    "T1: macro trend question tailored to {company}'s sector — e.g. 'What trends are most impacting...'",
    "T2: follow-on trend question"
  ],
  "insights": [
    "I1: personal/reflective question — e.g. 'What surprises you most about...'",
    "I2: 'How has [domain] changed most since you joined {company}?'"
  ],
  "advice": [
    "A1: make them the hero — e.g. 'If you were me, what would you be doing right now to best prepare for a role in [domain]?'"
  ],
  "resources": [
    "R1: pivot question — 'What resources do you recommend I look into next?' (open-ended to invite a name referral)",
    "R2: fallback if they deflect — 'What's the most important 10 minutes of reading you do to stay current in this space?'"
  ],
  "assignments": [
    "A1: 'What does a great first 90 days look like in a role like yours?' — signals preparation not desperation"
  ],
  "closing_ask": "End-of-meeting script: 'You've given me a lot to think about. I'm going to take the weekend to reflect — is it okay if I reach back out with any further questions?' [then follow up 1 week later]"
}}"""


def generate_tiara_prep(
    contact_name: str,
    contact_role: str,
    company: str,
    role_context: str = "",
) -> dict:
    """Generate TIARA informational meeting prep via Claude Opus."""
    prompt = _TIARA_PROMPT.format(
        contact_name = contact_name,
        contact_role = contact_role,
        company      = company,
        profile      = EXECUTIVE_PROFILE,
        role_context = f"Context: {role_context}" if role_context else "",
    )

    client  = anthropic.Anthropic()
    message = client.messages.create(
        model      = MODEL_OPUS,
        max_tokens = 1000,
        messages   = [{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


# ── Tracking Operations ───────────────────────────────────────────────────────

def add_outreach(
    records: list[OutreachRecord],
    company: str,
    contact_name: str,
    contact_role: str,
    channel: str = "email",
    contact_email: str = "",
    sent_date: Optional[str] = None,
    generated_subject: str = "",
    generated_body: str = "",
) -> OutreachRecord:
    """Add a new outreach record with 3B7 dates pre-computed."""
    today = date.fromisoformat(sent_date) if sent_date else date.today()
    follow_up_due       = _add_business_days(today, 3)
    second_contact_due  = _add_business_days(today, 7)

    record = OutreachRecord(
        company             = company,
        contact_name        = contact_name,
        contact_role        = contact_role,
        contact_email       = contact_email,
        channel             = channel,
        sent_date           = today.isoformat(),
        status              = "sent",
        follow_up_due       = follow_up_due.isoformat(),
        second_contact_due  = second_contact_due.isoformat(),
        generated_subject   = generated_subject,
        generated_email     = generated_body,
    )

    # Check if record already exists — update instead of duplicate
    existing = _find_record(records, company, contact_name)
    if existing:
        idx = records.index(existing)
        records[idx] = record
    else:
        records.append(record)

    return record


def mark_responded(
    records: list[OutreachRecord],
    company: str,
    contact_name: str,
    is_booster: bool = False,
) -> Optional[OutreachRecord]:
    """Mark a contact as responded. is_booster=True if they replied within 3 business days."""
    record = _find_record(records, company, contact_name)
    if not record:
        console.print(f"[yellow]No outreach record found for {contact_name} @ {company}[/yellow]")
        return None
    record.status = "booster" if is_booster else "responded"
    return record


def mark_referral(
    records: list[OutreachRecord],
    company: str,
    contact_name: str,
    referral_contact: str,
) -> Optional[OutreachRecord]:
    record = _find_record(records, company, contact_name)
    if not record:
        return None
    record.referral_received = True
    record.referral_contact  = referral_contact
    return record


def get_conversation_history(outreach_id: int) -> List[dict]:
    """
    Retrieve full conversation history for an outreach record.
    Returns list of messages sorted by date, with last 10 messages or ~3KB context max.

    Args:
        outreach_id: ID of OutreachRecord

    Returns:
        List of dicts: [{date, from_email, from_name, subject, body_preview}, ...]
    """
    try:
        with Session(engine) as session:
            messages = session.query(ConversationMessage).filter(
                ConversationMessage.outreach_record_id == outreach_id
            ).order_by(ConversationMessage.message_date.asc()).all()

            if not messages:
                return []

            # Limit to last 10 messages and ~3KB of context
            result = []
            total_chars = 0
            max_chars = 3000

            # Reverse to get last 10, but keep original order in result
            for msg in reversed(messages[-10:]):
                body_preview = msg.body_full[:200] if msg.body_full else ""  # 200 char preview
                msg_dict = {
                    "date": msg.message_date,
                    "from_email": msg.from_email,
                    "from_name": msg.from_name or "Unknown",
                    "subject": msg.subject or "(no subject)",
                    "body_preview": body_preview,
                    "message_type": msg.message_type,
                }
                total_chars += len(str(msg_dict))
                if total_chars > max_chars:
                    break
                result.append(msg_dict)

            return result
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to retrieve conversation history: {e}[/yellow]")
        return []


def get_due_actions(records: list[OutreachRecord]) -> list[dict]:
    """
    Return list of actionable 3B7 items due today or overdue.
    Each item has: type, company, contact, due_date, instruction.
    """
    today   = date.today()
    actions = []

    for r in records:
        if r.status in ("booster", "obligate", "closed"):
            continue

        # Day-3 action: contact a second person in parallel
        if r.follow_up_due and r.status == "sent":
            due = date.fromisoformat(r.follow_up_due)
            if today >= due:
                actions.append({
                    "type":        "day_3_parallel",
                    "company":     r.company,
                    "contact":     r.contact_name,
                    "due_date":    r.follow_up_due,
                    "overdue":     today > due,
                    "instruction": (
                        f"No response from {r.contact_name} @ {r.company} after 3 business days. "
                        f"Identify a SECOND contact at {r.company} and send the same email via a "
                        f"different channel. Do not wait — hedge your bets now."
                    ),
                })

        # Day-7 action: follow up with original contact via different channel
        if r.second_contact_due and r.status == "sent":
            due = date.fromisoformat(r.second_contact_due)
            if today >= due:
                next_channel = {
                    "linkedin_group":   "email (via Hunter.io)",
                    "email":            "LinkedIn connection request (customized)",
                    "linkedin_connect": "email (via Hunter.io)",
                }.get(r.channel, "different channel")
                actions.append({
                    "type":        "day_7_followup",
                    "company":     r.company,
                    "contact":     r.contact_name,
                    "due_date":    r.second_contact_due,
                    "overdue":     today > due,
                    "instruction": (
                        f"Send {r.contact_name} the SAME email via {next_channel}. "
                        f"Do not reference the previous message — assume they missed it. "
                        f"This is your one follow-up. If no response after this, move on."
                    ),
                })

    # Sort overdue first
    actions.sort(key=lambda a: (not a["overdue"], a["due_date"]))
    return actions


# ── Display ───────────────────────────────────────────────────────────────────

def print_status(records: list[OutreachRecord]) -> None:
    actions = get_due_actions(records)

    # Due actions panel
    if actions:
        console.print(Panel(
            f"[bold red]{len(actions)} action(s) due[/bold red]",
            title="3B7 Follow-up Queue",
            border_style="red"
        ))
        for a in actions:
            overdue_tag = "[red]OVERDUE[/red] " if a["overdue"] else "[yellow]DUE[/yellow] "
            console.print(f"\n{overdue_tag}[bold]{a['company']}[/bold] — {a['contact']} ({a['type'].replace('_', ' ')})")
            console.print(f"  {a['instruction']}")
    else:
        console.print(Panel("[green]No follow-ups due.[/green]", border_style="green"))

    # Summary table
    if records:
        table = Table(title="Active Outreaches", box=box.ROUNDED)
        table.add_column("Company",    style="bold", min_width=18)
        table.add_column("Contact",    min_width=16)
        table.add_column("Channel",    width=16)
        table.add_column("Sent",       width=12)
        table.add_column("Status",     width=16)
        table.add_column("Booster",    width=10)

        status_colors = {
            "sent":       "white",
            "responded":  "yellow",
            "booster":    "green",
            "obligate":   "red",
            "no_response":"dim",
            "closed":     "blue",
        }

        for r in sorted(records, key=lambda x: x.sent_date, reverse=True):
            color = status_colors.get(r.status, "white")
            booster = "[green]✓ Booster[/green]" if r.status == "booster" else ("Referral ✓" if r.referral_received else "—")
            table.add_row(
                r.company,
                r.contact_name,
                r.channel,
                r.sent_date,
                f"[{color}]{r.status}[/{color}]",
                booster,
            )
        console.print(table)

        boosters  = sum(1 for r in records if r.status == "booster")
        referrals = sum(1 for r in records if r.referral_received)
        console.print(f"\n[bold]Boosters: {boosters}[/bold] · Referrals received: {referrals} · Total outreaches: {len(records)}")
    else:
        console.print("[dim]No outreach records yet. Start with:[/dim]")
        console.print("[dim]  python3 orchestrate.py outreach --company Stripe --contact \"Jane Smith\" --role CPO[/dim]")


def _print_email(result: dict, company: str, contact: str) -> None:
    subject    = result.get("subject", "")
    body       = result.get("body", "")
    word_count = result.get("word_count", len(body.split()))
    connection = result.get("connection_used", "")

    wc_color = "green" if word_count <= 75 else "red"
    console.print(Panel(
        f"[bold]Subject:[/bold] {subject}\n\n"
        f"{body}\n\n"
        f"[dim]Word count: [{wc_color}]{word_count}[/{wc_color}]/75 · Connection: {connection}[/dim]",
        title=f"6-Point Email → {contact} @ {company}",
        border_style="blue",
    ))
    if word_count > 75:
        console.print("[red]WARNING: Body exceeds 75 words. Edit before sending.[/red]")

    console.print("\n[dim]To log this as sent:[/dim]")
    console.print(f'[dim]  python3 orchestrate.py outreach --track --company "{company}" --contact "{contact}" --channel email[/dim]')


def _print_tiara(result: dict, company: str, contact: str) -> None:
    lines = [f"# TIARA Prep — {contact} @ {company}", ""]

    for section, key in [
        ("Small Talk Openers", "small_talk"),
        ("T — Trends", "trends"),
        ("I — Insights", "insights"),
        ("A — Advice (make them the hero)", "advice"),
        ("R — Resources (pivot to referral)", "resources"),
        ("A — Assignments", "assignments"),
    ]:
        items = result.get(key, [])
        if items:
            lines.append(f"## {section}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    closing = result.get("closing_ask", "")
    if closing:
        lines.append("## Closing Ask")
        lines.append(f"_{closing}_")
        lines.append("")

    console.print(Panel("\n".join(lines), title=f"TIARA Prep — {contact} @ {company}", border_style="cyan"))


def _write_report(records: list[OutreachRecord]) -> None:
    actions  = get_due_actions(records)
    boosters = [r for r in records if r.status == "booster"]
    now      = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Outreach Tracker Report",
        f"_Generated: {now} · {len(records)} total outreaches_",
        "",
        f"**Boosters:** {len(boosters)} · "
        f"**Referrals:** {sum(1 for r in records if r.referral_received)} · "
        f"**Actions due:** {len(actions)}",
        "",
    ]

    if actions:
        lines += ["## Actions Due (3B7)", ""]
        for a in actions:
            tag = "🔴 OVERDUE" if a["overdue"] else "🟡 DUE"
            lines.append(f"### {tag} — {a['company']} ({a['type'].replace('_', ' ')})")
            lines.append(f"{a['instruction']}")
            lines.append("")

    lines += ["## All Outreaches", ""]
    lines += ["| Company | Contact | Channel | Sent | Status | Booster |", "|---------|---------|---------|------|--------|---------|"]
    for r in sorted(records, key=lambda x: x.sent_date, reverse=True):
        booster = "✓" if r.status == "booster" else ""
        lines.append(f"| {r.company} | {r.contact_name} | {r.channel} | {r.sent_date} | {r.status} | {booster} |")

    TRACKER_REPORT.write_text("\n".join(lines), encoding="utf-8")


# ── Entry Point ───────────────────────────────────────────────────────────────

def run(args=None) -> str:
    company        = getattr(args, "company", None)
    contact        = getattr(args, "contact", None)
    role           = getattr(args, "role", "")
    channel        = getattr(args, "channel", "email")
    contact_email  = getattr(args, "email", "")
    notes          = getattr(args, "notes", "")
    do_add         = getattr(args, "add", False)
    do_tiara       = getattr(args, "tiara", False)
    do_track       = getattr(args, "track", False)
    do_status      = getattr(args, "status", False)
    mark_responded_str = getattr(args, "mark_responded", None)
    is_booster     = getattr(args, "booster", False)
    referral       = getattr(args, "referral", None)

    records = load_tracker()

    # ── Show status / due actions ────────────────────────────────────────────
    if do_status or (not company and not mark_responded_str):
        print_status(records)
        _write_report(records)
        return f"Outreach status: {len(records)} records, {len(get_due_actions(records))} actions due"

    # ── Mark responded / booster ─────────────────────────────────────────────
    if mark_responded_str:
        if ":" not in mark_responded_str:
            console.print("[red]Format: --mark-responded \"Company:Contact Name\"[/red]")
            return "Error: invalid format"
        co, ct = mark_responded_str.split(":", 1)
        record = mark_responded(records, co.strip(), ct.strip(), is_booster)
        if record:
            if referral:
                mark_referral(records, co.strip(), ct.strip(), referral)
                console.print(f"[green]Referral from {ct.strip()} noted: {referral}[/green]")
            label = "[bold green]BOOSTER[/bold green]" if is_booster else "responded"
            console.print(f"[green]Marked {ct.strip()} @ {co.strip()} as {label}[/green]")
            save_tracker(records)
            _write_report(records)
        return f"Updated: {mark_responded_str}"

    # ── Require company + contact for generation/tracking ────────────────────
    if not company:
        console.print("[red]--company required[/red]")
        return "Error: --company required"
    if not contact and not do_status:
        console.print("[red]--contact required[/red]")
        return "Error: --contact required"

    # ── Quick-add new contact (already emailed, no Claude) ───────────────────
    if do_add:
        if not company:
            console.print("[red]--company required[/red]")
            return "Error: --company required"
        if not contact:
            console.print("[red]--contact required[/red]")
            return "Error: --contact required"
        record = add_outreach(
            records, company, contact, role, channel,
            contact_email=contact_email,
        )
        if notes:
            record.notes = notes
        save_tracker(records)
        _write_report(records)
        console.print(Panel(
            f"[green]Contact added and outreach logged.[/green]\n\n"
            f"Company  : {company}\n"
            f"Contact  : {contact}{f' ({role})' if role else ''}\n"
            f"Email    : {contact_email or '[not set]'}\n"
            f"Channel  : {channel}\n"
            f"Sent     : {record.sent_date}\n"
            f"Notes    : {notes or '—'}\n\n"
            f"[bold]3B7 Schedule:[/bold]\n"
            f"  Day-3 ({record.follow_up_due}): identify a second contact at {company}\n"
            f"  Day-7 ({record.second_contact_due}): follow up via different channel\n\n"
            f"[dim]When they reply, gmail scan will auto-match and update status.[/dim]",
            title="Contact Tracked",
            border_style="green",
        ))
        return f"Added: {contact} @ {company}"

    # ── Log outreach as sent (no Claude) ─────────────────────────────────────
    if do_track:
        record = add_outreach(records, company, contact, role, channel)
        save_tracker(records)
        _write_report(records)
        console.print(Panel(
            f"[green]Outreach logged.[/green]\n\n"
            f"Company  : {company}\n"
            f"Contact  : {contact} ({role})\n"
            f"Channel  : {channel}\n"
            f"Sent     : {record.sent_date}\n"
            f"Day-3 due: {record.follow_up_due} — identify second contact\n"
            f"Day-7 due: {record.second_contact_due} — follow up via different channel",
            title="Outreach Tracked",
            border_style="green",
        ))
        return f"Tracked: {contact} @ {company}"

    # ── Generate TIARA prep ───────────────────────────────────────────────────
    if do_tiara:
        console.print(f"[dim]Generating TIARA prep for {contact} @ {company}...[/dim]")
        result = generate_tiara_prep(contact, role, company)
        _print_tiara(result, company, contact)
        return f"TIARA prep generated for {contact} @ {company}"

    # ── Generate 6-point email ────────────────────────────────────────────────
    console.print(f"[dim]Generating 6-point email for {contact} @ {company}...[/dim]")
    result = generate_six_point_email(contact, role, company)
    _print_email(result, company, contact)

    # Offer to auto-track
    console.print(f"\n[dim]Run with --track to log this as sent once you've sent it.[/dim]")
    return f"Email generated for {contact} @ {company} ({result.get('word_count', '?')} words)"
