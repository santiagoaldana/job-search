"""
Dashboard Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Single morning brief command: python3 orchestrate.py today

Reads all existing JSON data files — zero API calls, zero network requests.
Renders four zones in order of urgency:

  Zone 1 — Pulse        (booster funnel progress)
  Zone 2 — Actions Due  (overdue 3B7 + pending drafts)
  Zone 3 — Top LAMP     (top 5 warm targets)
  Zone 4 — Events       (next 14 days only)

Design principles:
  - One command replaces the 5-command morning routine
  - Every item shown has a concrete next action printed below it
  - Overdue = red, due today = yellow, upcoming = white, done = green
  - Nothing truncated — if it fits in 80 cols it shows, otherwise it wraps cleanly
  - Zero cognitive load: "what do I do right now?" is answered in Zone 2
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding
from rich import box

console = Console(width=88)

# ── Path helpers ──────────────────────────────────────────────────────────────

def _data() -> Path:
    from skills.shared import DATA_DIR
    return DATA_DIR

def _load(filename: str):
    p = _data() / filename
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


# ── Status symbols ─────────────────────────────────────────────────────────────

STATUS_ICON = {
    "not_started": "[dim]○[/dim]",
    "outreach_sent": "[cyan]●[/cyan]",
    "booster_found": "[bold yellow]★[/bold yellow]",
    "done": "[green]✓[/green]",
    # outreach tracker statuses
    "sent": "[cyan]●[/cyan]",
    "responded": "[yellow]◉[/yellow]",
    "booster": "[bold yellow]★[/bold yellow]",
    "obligate": "[green]✓[/green]",
    "no_response": "[dim]✗[/dim]",
    "closed": "[dim]–[/dim]",
}

STATUS_LABEL = {
    "not_started": "Start",
    "outreach_sent": "Sent",
    "booster_found": "Booster ★",
    "done": "Done",
    "sent": "Sent",
    "responded": "Responded",
    "booster": "Booster ★",
    "obligate": "Obligate",
    "no_response": "No response",
    "closed": "Closed",
}


# ── Zone 1: Pulse ─────────────────────────────────────────────────────────────

def _render_pulse(tracker: list, drafts: list) -> None:
    today = date.today()

    # Outreach funnel counts (from full tracker including legacy contacts)
    active    = [r for r in tracker if not r.get("low_priority")]
    boosters  = sum(1 for r in active if r.get("status") == "booster")
    responded = sum(1 for r in active if r.get("status") in ("responded", "booster", "obligate"))
    waiting   = sum(1 for r in active if r.get("status") == "sent")
    total_out = sum(1 for r in active if r.get("status") not in ("closed",))

    pending_drafts = sum(1 for d in drafts if d.get("status") == "pending")

    # Overdue actions
    overdue_count = 0
    for r in active:
        if r.get("status") == "sent":
            for field in ("follow_up_due", "second_contact_due"):
                due_str = r.get(field, "")
                if due_str:
                    try:
                        if date.fromisoformat(due_str) <= today:
                            overdue_count += 1
                            break
                    except ValueError:
                        pass

    # Booster progress bar (target = 6 boosters per Dalton method)
    TARGET = 6
    filled = min(boosters, TARGET)
    bar = "█" * filled + "░" * (TARGET - filled)

    # Date header
    day_str  = today.strftime("%A %b %-d")
    week_num = today.isocalendar()[1]

    # Build pulse line
    funnel_parts = []
    if boosters:
        funnel_parts.append(f"[bold yellow]Boosters: {boosters}[/bold yellow]")
    else:
        funnel_parts.append(f"[dim]Boosters: 0[/dim]")
    funnel_parts.append(f"[yellow]Responded: {responded}[/yellow]")
    funnel_parts.append(f"[cyan]Waiting: {waiting}[/cyan]")
    if pending_drafts:
        funnel_parts.append(f"[magenta]Drafts: {pending_drafts}[/magenta]")
    if overdue_count:
        funnel_parts.append(f"[bold red]Overdue: {overdue_count}[/bold red]")

    funnel_str = "  │  ".join(funnel_parts)
    booster_pct = int(boosters / TARGET * 100)

    console.print()
    console.print(Rule(
        f"[bold]JOB SEARCH DASHBOARD[/bold]  [dim]{day_str}[/dim]",
        style="bold blue"
    ))
    console.print(f"  {funnel_str}")
    console.print(
        f"  [dim]Booster goal:[/dim] [{bar}] "
        f"[bold]{boosters}/{TARGET}[/bold]  "
        f"[dim]({booster_pct}% of target)[/dim]"
    )
    console.print(Rule(style="blue"))


# ── Zone 2: Actions Due ───────────────────────────────────────────────────────

def _render_actions(tracker: list, drafts: list) -> None:
    today = date.today()
    actions = []

    active = [r for r in tracker if not r.get("low_priority")]

    for r in active:
        company = r.get("company", "")
        contact = r.get("contact_name", "")
        status  = r.get("status", "")

        if status == "sent":
            for field, label, instruction in [
                (
                    "follow_up_due",
                    "Day-3",
                    f"Find a 2nd contact at [cyan]{company}[/cyan] and send the same email in parallel",
                ),
                (
                    "second_contact_due",
                    "Day-7",
                    f"Re-send to [cyan]{contact}[/cyan] via a different channel (used: {r.get('channel','email')})",
                ),
            ]:
                due_str = r.get(field, "")
                if not due_str:
                    continue
                try:
                    due = date.fromisoformat(due_str)
                except ValueError:
                    continue

                days_diff = (today - due).days
                if days_diff >= 0:
                    actions.append({
                        "overdue": days_diff > 0,
                        "days_diff": days_diff,
                        "due": due,
                        "label": label,
                        "company": company,
                        "contact": contact,
                        "instruction": instruction,
                        "command": (
                            f'python3 orchestrate.py outreach --add --company "{company}" '
                            f'--contact "New Contact" --role "Title" --channel linkedin_group'
                        ) if field == "follow_up_due" else (
                            f'python3 orchestrate.py outreach --company "{company}" '
                            f'--contact "{contact}" --role "{r.get("contact_role","")}"'
                        ),
                    })

        elif status == "responded":
            # Harvest cycle: 30+ days since last contact
            last = r.get("last_contact_date") or r.get("sent_date", "")
            if last and not r.get("referral_received"):
                try:
                    last_dt = date.fromisoformat(last[:10])
                    elapsed = (today - last_dt).days
                    if elapsed >= 30:
                        actions.append({
                            "overdue": elapsed > 35,
                            "days_diff": elapsed - 30,
                            "due": last_dt + timedelta(days=30),
                            "label": "Harvest",
                            "company": company,
                            "contact": contact,
                            "instruction": f"Monthly check-in with [cyan]{contact}[/cyan] — stay top-of-mind, share something useful",
                            "command": f'python3 orchestrate.py outreach --company "{company}" --contact "{contact}" --role "{r.get("contact_role","")}"',
                        })
                except ValueError:
                    pass

    actions.sort(key=lambda a: (-a["days_diff"], a["due"].isoformat()))

    pending_drafts = [d for d in drafts if d.get("status") == "pending"]
    pending_count  = len(pending_drafts)

    has_anything = actions or pending_count

    console.print()
    console.print(f"[bold]TODAY'S ACTIONS[/bold]")
    console.print()

    if not has_anything:
        console.print("  [green]✓ Nothing overdue. Good standing.[/green]")
        console.print()
        return

    if actions:
        for a in actions:
            tag_color = "bold red" if a["overdue"] else "yellow"
            tag_label = f"OVERDUE +{a['days_diff']}d" if a["overdue"] else f"DUE {a['due'].strftime('%b %-d')}"
            tag       = f"[{tag_color}]{tag_label:>12}[/{tag_color}]"

            co_ct = f"[bold]{a['company']}[/bold] — {a['contact']}"
            label = f"[dim]{a['label']}[/dim]"

            console.print(f"  {tag}  {co_ct}  {label}")
            console.print(f"           {a['instruction']}")
            console.print(f"           [dim]→ {a['command']}[/dim]")
            console.print()

    if pending_count:
        oldest = None
        for d in pending_drafts:
            ts = d.get("created_at", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts).date()
                    if oldest is None or dt < oldest:
                        oldest = dt
                except ValueError:
                    pass
        age_str = f", oldest {(today - oldest).days}d ago" if oldest else ""

        console.print(
            f"  [magenta]{'DRAFTS':>12}[/magenta]  "
            f"[bold]{pending_count} follow-up emails[/bold] awaiting approval{age_str}"
        )
        console.print(f"           [dim]→ python3 orchestrate.py gmail review --batch 10[/dim]")
        console.print()


# ── Zone 3: Top LAMP Targets ──────────────────────────────────────────────────

def _render_lamp(lamp: list, tracker: list) -> None:
    if not lamp:
        console.print("[dim]No LAMP list found — run: python3 orchestrate.py lamp[/dim]")
        return

    # Build lookup: company → outreach status from tracker
    tracker_status: dict[str, str] = {}
    for r in tracker:
        co = r.get("company", "").lower().strip()
        st = r.get("status", "")
        # Prefer "better" statuses (booster > responded > sent)
        priority = {"booster": 4, "responded": 3, "obligate": 3, "sent": 2, "no_response": 1}
        if co not in tracker_status or priority.get(st, 0) > priority.get(tracker_status[co], 0):
            tracker_status[co] = st

    # Sort: motivation DESC, then lamp_score DESC
    sorted_lamp = sorted(lamp, key=lambda e: (-e.get("motivation", 5), -e.get("lamp_score", 0)))

    # Warm targets (have contacts)
    warm  = [e for e in sorted_lamp if e.get("contacts")]
    # Build targets (no contacts, motivation ≥ 7)
    build = [e for e in sorted_lamp if not e.get("contacts") and e.get("motivation", 5) >= 7]

    console.print(f"[bold]TOP LAMP TARGETS[/bold]")
    console.print()

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("#",       width=3,  justify="right")
    table.add_column("Company", width=20)
    table.add_column("M",       width=2,  justify="center")
    table.add_column("Score",   width=5,  justify="center")
    table.add_column("Contact", width=24)
    table.add_column("Status",  width=14)
    table.add_column("Action",  width=14)

    shown = 0
    for i, entry in enumerate(warm[:8], 1):
        company  = entry.get("company", "")
        mot      = entry.get("motivation", 5)
        score    = entry.get("lamp_score", 0)
        contacts = entry.get("contacts", [])
        lamp_status = entry.get("status", "not_started")

        # Override with actual outreach tracker status if exists
        actual_status = tracker_status.get(company.lower().strip(), lamp_status)

        contact_str = contacts[0] if contacts else "—"
        if len(contacts) > 1:
            contact_str += f" +{len(contacts)-1}"

        icon  = STATUS_ICON.get(actual_status, "○")
        label = STATUS_LABEL.get(actual_status, actual_status)

        mot_color = "bold green" if mot >= 8 else ("yellow" if mot >= 6 else "dim")

        # Suggested action
        if actual_status == "not_started":
            action = "→ outreach"
        elif actual_status == "sent":
            action = "→ 3B7 check"
        elif actual_status in ("responded", "obligate"):
            action = "→ harvest"
        elif actual_status == "booster":
            action = "→ referral ask"
        else:
            action = ""

        table.add_row(
            str(i),
            company[:20],
            f"[{mot_color}]{mot}[/{mot_color}]",
            f"{score:.1f}",
            contact_str[:24],
            f"{icon} {label}",
            f"[dim]{action}[/dim]",
        )
        shown += 1

    console.print(table)

    # Build targets — compact list
    if build:
        build_names = ", ".join(e.get("company", "") for e in build[:5])
        extra = len(build) - 5 if len(build) > 5 else 0
        suffix = f" +{extra} more" if extra else ""
        console.print(
            f"  [dim]Build targets (no contacts yet, mot≥7):[/dim] "
            f"[dim]{build_names}{suffix}[/dim]"
        )
        console.print(
            f"  [dim]→ Find 1-2 employees on LinkedIn (MIT Sloan alumni search or FinTech communities)[/dim]"
        )

    ready = [e for e in warm[:8] if tracker_status.get(e.get("company","").lower().strip(), "not_started") == "not_started"]
    if ready:
        first = ready[0]
        contacts = first.get("contacts", [])
        console.print()
        console.print(
            f"  [green]Ready to outreach:[/green] [bold]{first['company']}[/bold]"
            + (f" via {contacts[0]}" if contacts else "")
        )
        console.print(
            f"  [dim]→ python3 orchestrate.py outreach "
            f"--company \"{first['company']}\" "
            f"--contact \"{contacts[0] if contacts else 'Name'}\" "
            f"--role \"Title\"[/dim]"
        )
    console.print()


# ── Zone 4: Upcoming Events ───────────────────────────────────────────────────

def _render_events(events: list) -> None:
    today     = date.today()
    cutoff    = today + timedelta(days=14)
    soon_cutoff = today + timedelta(days=7)

    upcoming = []
    for e in events:
        date_str = e.get("date", "")
        if not date_str or date_str.lower() in ("tbd", "recurring", "various"):
            continue
        try:
            ev_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        if today <= ev_date <= cutoff:
            # Only show job-search-relevant events (scored or STRATEGIC/HIGH_PROBABILITY)
            category = e.get("category", "")
            net_score = e.get("net_score", 0)
            if category in ("STRATEGIC", "HIGH_PROBABILITY") or net_score >= 5:
                upcoming.append((ev_date, e))

    upcoming.sort(key=lambda x: (-x[1].get("net_score", 0), x[0]))
    upcoming = upcoming[:8]  # cap at 8 events

    console.print(f"[bold]NEXT 14 DAYS — EVENTS[/bold]")
    console.print()

    if not upcoming:
        console.print(f"  [dim]No events in next 14 days.[/dim]")
        console.print(f"  [dim]Next check: python3 orchestrate.py events[/dim]")
        console.print()
        return

    for ev_date, e in upcoming:
        name     = e.get("name", "Unknown")
        location = e.get("location", "")
        score    = e.get("net_score", 0)
        is_soon  = ev_date <= soon_cutoff

        days_away = (ev_date - today).days
        if days_away == 0:
            when = "[bold red]TODAY[/bold red]"
        elif days_away == 1:
            when = "[bold yellow]TOMORROW[/bold yellow]"
        else:
            when = f"[cyan]{ev_date.strftime('%b %-d')}[/cyan]"

        urgency = " [bold red]⚠ Register soon[/bold red]" if is_soon else ""
        loc_str = f"  [dim]{location}[/dim]" if location else ""

        console.print(f"  {when}  [bold]{name[:50]}[/bold]{urgency}")
        if loc_str:
            console.print(f"         {loc_str}")

    console.print()


# ── Zone 5: Quick Reference ───────────────────────────────────────────────────

def _render_quick_ref() -> None:
    console.print(Rule("[dim]Quick Commands[/dim]", style="dim"))
    lines = [
        ("Add new contact",    'python3 orchestrate.py outreach --add --company "X" --contact "Name" --role "Title"'),
        ("Review drafts",      "python3 orchestrate.py gmail review --batch 10"),
        ("Generate email",     'python3 orchestrate.py outreach --company "X" --contact "Name" --role "Title"'),
        ("Update LAMP",        'python3 orchestrate.py lamp --set-motivation "Stripe:9"'),
        ("Run gmail scan",     "python3 orchestrate.py gmail scan"),
        ("Full pipeline",      "python3 orchestrate.py all --no-enrich"),
    ]
    for label, cmd in lines:
        console.print(f"  [dim]{label:<22}[/dim]  [dim]{cmd}[/dim]")
    console.print()


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run(args=None) -> str:
    tracker = _load("outreach_tracker.json")
    lamp    = _load("lamp_list.json")
    drafts  = _load("pending_drafts.json")
    events  = _load("events_cache.json")

    # Normalize tracker: handle both list (current) and legacy formats
    if isinstance(tracker, dict):
        tracker = list(tracker.values())

    # Normalize lamp: handle list of dicts
    if isinstance(lamp, dict):
        lamp = list(lamp.values())

    _render_pulse(tracker, drafts)
    _render_actions(tracker, drafts)
    _render_lamp(lamp, tracker)
    _render_events(events)
    _render_quick_ref()

    # Return a summary string for orchestrate.py
    pending = sum(1 for d in drafts if d.get("status") == "pending")
    boosters = sum(1 for r in tracker if r.get("status") == "booster")
    return f"Dashboard: {boosters} boosters, {pending} drafts pending"
