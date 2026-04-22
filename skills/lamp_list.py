"""
LAMP List Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Implements Steve Dalton's 2-Hour Job Search LAMP methodology:
  L = List of employers
  A = Advocacy (1st-degree contacts at that company)
  M = Motivation (personal score 1-10: "how fired up are you to persist here?")
  P = Postings (relevant open roles at that company right now)

Scoring and sort order follows Dalton exactly:
  lamp_score = (motivation * 0.5) + (postings * 0.3) + (advocacy * 0.2)
  Sort: motivation DESC first, then postings DESC, then advocacy DESC

The LAMP list is your ranked consideration set — not just where jobs are posted,
but where you have the motivation to persist through being ignored.

Usage:
  python3 orchestrate.py lamp                                    # Build from leads + contacts
  python3 orchestrate.py lamp --set-motivation "Stripe:9,Citi:7"  # Override motivation
  python3 orchestrate.py lamp --set-status "Stripe:booster_found" # Update progress
"""

import csv
import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from skills.shared import DATA_DIR, CONTACTS_CSV

console = Console()

LAMP_CACHE = DATA_DIR / "lamp_list.json"
LAMP_REPORT = DATA_DIR / "lamp_report.md"

VALID_STATUSES = {"not_started", "outreach_sent", "booster_found", "done"}


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class LAMPEntry:
    company: str
    motivation: int = 5          # 1-10, user-set
    postings_score: int = 1      # 1-10, derived from leads_pipeline.json
    advocacy_score: int = 1      # 1-10, derived from contacts CSV
    lamp_score: float = 0.0      # computed: (M*0.5)+(P*0.3)+(A*0.2)
    contacts: list = field(default_factory=list)    # 1st-degree contact names
    open_roles: list = field(default_factory=list)  # matching role titles
    status: str = "not_started"  # not_started | outreach_sent | booster_found | done
    notes: str = ""
    last_updated: str = ""


def _compute_lamp_score(motivation: int, postings: int, advocacy: int) -> float:
    return round((motivation * 0.5) + (postings * 0.3) + (advocacy * 0.2), 2)


# ── Company Name Normalization ────────────────────────────────────────────────

_STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|llc\.?|corp\.?|ltd\.?|limited|incorporated|co\.?|company|group|holdings?)\b",
    re.IGNORECASE
)

def _normalize(name: str) -> str:
    name = _STRIP_SUFFIXES.sub("", name).strip().lower()
    return re.sub(r"\s+", " ", name).strip()


def _companies_match(a: str, b: str) -> bool:
    return _normalize(a) == _normalize(b)


# ── Data Loading ──────────────────────────────────────────────────────────────

def _load_leads(leads_path: Path) -> dict[str, list[str]]:
    """
    Load leads_pipeline.json. Returns dict of company -> [role titles].
    Postings score: 0 roles = 1, 1-2 roles = 5, 3+ roles = 10.
    """
    if not leads_path.exists():
        return {}
    try:
        leads = json.loads(leads_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    company_roles: dict[str, list[str]] = {}
    for lead in leads:
        co = lead.get("company", "").strip()
        title = lead.get("title", "").strip()
        if co:
            company_roles.setdefault(co, [])
            if title:
                company_roles[co].append(title)
    return company_roles


def _load_contacts_companies(contacts_csv: Path) -> dict[str, list[str]]:
    """
    Load LinkedIn contacts CSV. Returns dict of normalized_company -> [contact full names].
    """
    if not contacts_csv or not contacts_csv.exists():
        return {}

    company_contacts: dict[str, list[str]] = {}
    try:
        with open(contacts_csv, encoding="utf-8-sig", errors="replace") as f:
            # Skip LinkedIn header lines (first 3 lines are metadata)
            content = f.read()
        lines = content.splitlines()
        # Find the CSV header row
        header_idx = next(
            (i for i, l in enumerate(lines) if "first name" in l.lower() or "firstname" in l.lower()),
            0
        )
        csv_lines = "\n".join(lines[header_idx:])
        reader = csv.DictReader(csv_lines.splitlines())
        headers = {k.strip().lower(): k for k in (reader.fieldnames or [])}

        first_key  = headers.get("first name") or headers.get("firstname", "")
        last_key   = headers.get("last name")  or headers.get("lastname", "")
        co_key     = headers.get("company", "")

        for row in reader:
            co = row.get(co_key, "").strip()
            first = row.get(first_key, "").strip()
            last  = row.get(last_key, "").strip()
            name  = f"{first} {last}".strip()
            if co and name:
                norm = _normalize(co)
                company_contacts.setdefault(norm, [])
                company_contacts[norm].append(name)
    except Exception as e:
        console.print(f"[dim yellow][LAMP] Could not load contacts: {e}[/dim yellow]")

    return company_contacts


# ── Score Helpers ─────────────────────────────────────────────────────────────

def _postings_score(role_count: int) -> int:
    if role_count == 0:
        return 1
    if role_count <= 2:
        return 5
    return 10


def _advocacy_score(contact_count: int) -> int:
    if contact_count == 0:
        return 1
    if contact_count == 1:
        return 7
    return 10


# ── Build / Load / Save ───────────────────────────────────────────────────────

def build_lamp_list(
    leads_path: Path,
    contacts_csv: Optional[Path] = None,
    existing: Optional[list] = None,
) -> list[LAMPEntry]:
    """
    Build LAMP list from leads_pipeline.json + contacts CSV.
    Preserves motivation/status/notes from existing entries.
    """
    company_roles    = _load_leads(leads_path)
    company_contacts = _load_contacts_companies(contacts_csv) if contacts_csv else {}

    # Existing entries: preserve user-set motivation, status, notes
    existing_map: dict[str, LAMPEntry] = {}
    if existing:
        for e in existing:
            existing_map[_normalize(e.company)] = e

    entries: dict[str, LAMPEntry] = {}

    # Seed from leads (companies with open roles)
    for company, roles in company_roles.items():
        norm = _normalize(company)
        # Find matching contacts
        contacts = company_contacts.get(norm, [])
        # Also check partial matches
        if not contacts:
            for co_norm, names in company_contacts.items():
                if norm in co_norm or co_norm in norm:
                    contacts = names
                    break

        prev = existing_map.get(norm)
        motivation    = prev.motivation if prev else 5
        status        = prev.status     if prev else "not_started"
        notes         = prev.notes      if prev else ""
        postings      = _postings_score(len(roles))
        advocacy      = _advocacy_score(len(contacts))
        lamp_score    = _compute_lamp_score(motivation, postings, advocacy)

        entries[norm] = LAMPEntry(
            company       = company,
            motivation    = motivation,
            postings_score= postings,
            advocacy_score= advocacy,
            lamp_score    = lamp_score,
            contacts      = contacts,
            open_roles    = roles,
            status        = status,
            notes         = notes,
            last_updated  = datetime.now().strftime("%Y-%m-%d"),
        )

    # Also seed from contacts (companies where we know people, even without open roles)
    # Only include if we have 2+ contacts there (stronger advocacy signal)
    for co_norm, contacts in company_contacts.items():
        if co_norm not in entries and len(contacts) >= 2:
            # Reconstruct display name from norm
            company = contacts[0].split(" ")[0] if contacts else co_norm.title()
            # Find original company name from CSV — use co_norm.title() as fallback
            prev      = existing_map.get(co_norm)
            motivation = prev.motivation if prev else 5
            status     = prev.status     if prev else "not_started"
            notes      = prev.notes      if prev else ""
            advocacy   = _advocacy_score(len(contacts))
            postings   = 1  # no open roles found
            lamp_score = _compute_lamp_score(motivation, postings, advocacy)

            # Use a proper company name: check if any lead has the same norm
            display_name = co_norm.title()
            for co, _ in company_roles.items():
                if _normalize(co) == co_norm:
                    display_name = co
                    break

            entries[co_norm] = LAMPEntry(
                company        = display_name,
                motivation     = motivation,
                postings_score = postings,
                advocacy_score = advocacy,
                lamp_score     = lamp_score,
                contacts       = contacts,
                open_roles     = [],
                status         = status,
                notes          = notes,
                last_updated   = datetime.now().strftime("%Y-%m-%d"),
            )

    # Preserve manually-added entries (motivation overridden by user, not in leads/contacts)
    # These are "build targets" — companies the user explicitly added with no data source yet.
    # Keep any existing entry with motivation >= 6 that didn't appear in the rebuild.
    for prev in (existing or []):
        norm = _normalize(prev.company)
        if norm not in entries and prev.motivation >= 6:
            entries[norm] = LAMPEntry(
                company        = prev.company,
                motivation     = prev.motivation,
                postings_score = prev.postings_score,
                advocacy_score = prev.advocacy_score,
                lamp_score     = _compute_lamp_score(prev.motivation, prev.postings_score, prev.advocacy_score),
                contacts       = prev.contacts,
                open_roles     = prev.open_roles,
                status         = prev.status,
                notes          = prev.notes,
                last_updated   = prev.last_updated,
            )

    # Sort: motivation DESC, then postings DESC, then advocacy DESC (Dalton order)
    sorted_entries = sorted(
        entries.values(),
        key=lambda e: (-e.motivation, -e.postings_score, -e.advocacy_score)
    )

    return sorted_entries


def save_lamp_list(entries: list[LAMPEntry], path: Path = LAMP_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load_lamp_list(path: Path = LAMP_CACHE) -> list[LAMPEntry]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [LAMPEntry(**r) for r in raw]
    except Exception:
        return []


def update_motivation(entries: list[LAMPEntry], motivation_str: str) -> list[LAMPEntry]:
    """Parse 'Stripe:9,Citi:7' and update matching entries. Recompute lamp_score."""
    updates: dict[str, int] = {}
    for pair in motivation_str.split(","):
        pair = pair.strip()
        if ":" not in pair:
            continue
        co, score = pair.rsplit(":", 1)
        try:
            updates[_normalize(co.strip())] = max(1, min(10, int(score.strip())))
        except ValueError:
            pass

    for entry in entries:
        norm = _normalize(entry.company)
        if norm in updates:
            entry.motivation = updates[norm]
            entry.lamp_score = _compute_lamp_score(
                entry.motivation, entry.postings_score, entry.advocacy_score
            )
            entry.last_updated = datetime.now().strftime("%Y-%m-%d")

    # Re-sort after motivation change
    return sorted(entries, key=lambda e: (-e.motivation, -e.postings_score, -e.advocacy_score))


def update_status(entries: list[LAMPEntry], status_str: str) -> list[LAMPEntry]:
    """Parse 'Stripe:booster_found' and update matching entry."""
    if ":" not in status_str:
        console.print(f"[red]Invalid --set-status format. Use 'Company:status'[/red]")
        return entries
    co, status = status_str.rsplit(":", 1)
    co     = co.strip()
    status = status.strip()
    if status not in VALID_STATUSES:
        console.print(f"[red]Invalid status '{status}'. Valid: {', '.join(VALID_STATUSES)}[/red]")
        return entries

    norm = _normalize(co)
    for entry in entries:
        if _normalize(entry.company) == norm:
            entry.status = status
            entry.last_updated = datetime.now().strftime("%Y-%m-%d")
            console.print(f"[green]Updated {entry.company} → {status}[/green]")
            return entries
    console.print(f"[yellow]Company '{co}' not found in LAMP list.[/yellow]")
    return entries


# ── Reporting ─────────────────────────────────────────────────────────────────

STATUS_COLORS = {
    "not_started":   "dim",
    "outreach_sent": "yellow",
    "booster_found": "green",
    "done":          "blue",
}

STATUS_LABELS = {
    "not_started":   "Not Started",
    "outreach_sent": "Outreach Sent",
    "booster_found": "Booster Found ✓",
    "done":          "Done ✓",
}


def _make_lamp_table(title: str, entries: list, numbered_from: int = 1) -> Table:
    table = Table(title=title, box=box.ROUNDED, show_lines=True)
    table.add_column("#",          style="dim",      no_wrap=True)
    table.add_column("Company",    style="bold",     no_wrap=True)
    table.add_column("Mot",        justify="center", no_wrap=True)
    table.add_column("Post",       justify="center", no_wrap=True)
    table.add_column("Adv",        justify="center", no_wrap=True)
    table.add_column("Score",      justify="center", no_wrap=True)
    table.add_column("1st-Degree Contacts")
    table.add_column("Open Roles")
    table.add_column("Status")

    for i, e in enumerate(entries, numbered_from):
        color = STATUS_COLORS.get(e.status, "dim")
        label = STATUS_LABELS.get(e.status, e.status)
        contacts_str = ", ".join(e.contacts[:2]) + ("…" if len(e.contacts) > 2 else "")
        roles_str = e.open_roles[0][:26] + "…" if e.open_roles and len(e.open_roles[0]) > 26 else (e.open_roles[0] if e.open_roles else "—")
        if len(e.open_roles) > 1:
            roles_str += f" +{len(e.open_roles)-1}"
        table.add_row(
            str(i), e.company,
            str(e.motivation), str(e.postings_score), str(e.advocacy_score), str(e.lamp_score),
            contacts_str or "—", roles_str,
            f"[{color}]{label}[/{color}]",
        )
    return table


def print_lamp_table(entries: list[LAMPEntry], top_n: int = 15) -> None:
    # Split into warm (has contacts) and build (no contacts yet, high motivation)
    warm  = [e for e in entries if len(e.contacts) > 0][:top_n]
    build = [e for e in entries if len(e.contacts) == 0 and e.motivation >= 7]
    build.sort(key=lambda e: (-e.motivation, -e.postings_score))
    build = build[:10]

    console.print(_make_lamp_table(f"LAMP — Warm Targets (existing contacts, top {len(warm)})", warm))
    if build:
        console.print(_make_lamp_table(f"LAMP — Build Targets (no contacts yet, motivation ≥ 7)", build))
        console.print("[yellow]Build targets: start by finding 1-2 employees on LinkedIn — MIT Sloan alumni search or FinTech communities[/yellow]")

    console.print(
        "\n[dim]Mot = Motivation (user-set 1-10) · Post = Postings · Adv = Advocacy · "
        "Score = (M×0.5)+(P×0.3)+(A×0.2)[/dim]"
    )
    console.print(
        "[dim]Set motivation: python3 orchestrate.py lamp --set-motivation \"Stripe:9,Citi:7\"[/dim]\n"
    )


def _write_report(entries: list[LAMPEntry], path: Path = LAMP_REPORT) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# LAMP List — Target Employer Ranking",
        f"_Generated: {now} · {len(entries)} employers · 2-Hour Job Search Method_",
        "",
        "Sorted by: Motivation (primary) → Postings → Advocacy",
        "Score = (Motivation × 0.5) + (Postings × 0.3) + (Advocacy × 0.2)",
        "",
        "| # | Company | M | P | A | Score | Status |",
        "|---|---------|---|---|---|-------|--------|",
    ]
    for i, e in enumerate(entries, 1):
        lines.append(
            f"| {i} | {e.company} | {e.motivation} | {e.postings_score} | "
            f"{e.advocacy_score} | {e.lamp_score} | {STATUS_LABELS.get(e.status, e.status)} |"
        )

    lines += ["", "---", ""]

    for i, e in enumerate(entries[:15], 1):
        lines.append(f"## {i}. {e.company}")
        if e.contacts:
            lines.append(f"**1st-degree contacts:** {', '.join(e.contacts)}")
        if e.open_roles:
            lines.append(f"**Open roles ({len(e.open_roles)}):**")
            for r in e.open_roles:
                lines.append(f"  - {r}")
        lines.append(f"**Status:** {STATUS_LABELS.get(e.status, e.status)}")
        if e.notes:
            lines.append(f"**Notes:** {e.notes}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Entry Point ───────────────────────────────────────────────────────────────

def run(args=None) -> str:
    from skills.shared import DATA_DIR, CONTACTS_CSV

    leads_path   = DATA_DIR / "leads_pipeline.json"
    contacts_csv = CONTACTS_CSV if CONTACTS_CSV.exists() else None

    set_motivation = getattr(args, "set_motivation", None)
    set_status     = getattr(args, "set_status", None)

    # Load existing to preserve user overrides
    existing = load_lamp_list()

    # If only updating status/motivation, no need to rebuild
    if (set_motivation or set_status) and existing:
        if set_motivation:
            existing = update_motivation(existing, set_motivation)
        if set_status:
            existing = update_status(existing, set_status)
        save_lamp_list(existing)
        _write_report(existing)
        print_lamp_table(existing)
        return f"LAMP list updated — {len(existing)} employers"

    # Full rebuild
    console.print("[dim]Building LAMP list from leads + contacts...[/dim]")
    entries = build_lamp_list(leads_path, contacts_csv, existing)

    if set_motivation:
        entries = update_motivation(entries, set_motivation)
    if set_status:
        entries = update_status(entries, set_status)

    save_lamp_list(entries)
    _write_report(entries)
    print_lamp_table(entries)

    msg = f"LAMP list built — {len(entries)} employers ranked. Saved to data/lamp_list.json"
    console.print(f"\n[green]{msg}[/green]")
    console.print("[dim]Next: set your motivation scores, then generate outreach emails.[/dim]")
    console.print("[dim]  python3 orchestrate.py lamp --set-motivation \"Stripe:9,Coinbase:8\"[/dim]")
    console.print("[dim]  python3 orchestrate.py outreach --company Stripe --contact \"Jane Smith\" --role CPO[/dim]")
    return msg
