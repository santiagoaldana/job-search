"""
Job Search Orchestration System — Main CLI
Santiago Aldana | Executive Job Search

Single entry point for all 5 modules.

Usage:
  python3 orchestrate.py all                                      # Full pipeline
  python3 orchestrate.py content                                  # Module 1: LinkedIn drafts
  python3 orchestrate.py events                                   # Module 2: Event discovery
  python3 orchestrate.py leads                                    # Module 3: Lead generation
  python3 orchestrate.py network --target "Stripe"                # Module 4: Network pathfinder
  python3 orchestrate.py cv --jd <url> --company Stripe --role CPO  # Module 5: CV synthesis

Global options:
  --no-enrich      Skip all Claude API calls (faster, lower cost)
  --contacts PATH  LinkedIn contacts CSV path (Modules 3, 4)
  --format         CV output format: pdf | html | both (default: both)

Run 'python3 orchestrate.py <command> --help' for module-specific options.
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

# Load .env before importing any module that uses API keys
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

BASE_DIR = Path(__file__).parent


# ── Subcommand Runners ────────────────────────────────────────────────────────

def run_content(args):
    from skills.content_intelligence import run
    console.print(Panel("[bold]Module 1 — Content Intelligence[/bold]\nGenerating LinkedIn post drafts from FinTech news", border_style="blue"))
    report = run(
        max_age_days=getattr(args, "days", 7),
        n_drafts=getattr(args, "drafts", 5),
        enrich=not getattr(args, "no_enrich", False),
    )
    console.print(Panel(f"[green]Content drafts saved to data/content_drafts.md[/green]", border_style="green"))
    return report


def run_leaders(args):
    from skills.leaders_watchlist import (
        add_leader, add_leader_from_url, scan_all_leaders,
        load_watchlist, show_watchlist, format_leaders_report, seed_watchlist,
    )
    seed_watchlist()
    enrich = not getattr(args, "no_enrich", False)

    if getattr(args, "add_url", None) and getattr(args, "add", None):
        console.print(Panel(
            f"[bold]Leaders — Add from URL[/bold]\n{args.add_url}",
            border_style="blue"
        ))
        try:
            leader = add_leader_from_url(args.add_url, args.add)
            console.print(Panel(
                f"[green]Added: {leader['name']} ({leader.get('organization', '')})[/green]",
                border_style="green"
            ))
        except ValueError as e:
            console.print(f"[yellow]{e}[/yellow]")
        return ""

    elif getattr(args, "add", None):
        console.print(Panel(f"[bold]Leaders — Add[/bold]\n{args.add}", border_style="blue"))
        topics = [t.strip() for t in args.topics.split(",") if t.strip()] if args.topics else []
        try:
            leader = add_leader(
                name=args.add,
                organization=args.org,
                substack_url=args.substack,
                luma_profile_url=args.luma,
                meetup_url=args.meetup,
                website_url=args.website,
                topics=topics,
                notes=args.notes,
            )
            console.print(Panel(
                f"[green]Added: {leader['name']} ({leader.get('organization', '')})[/green]",
                border_style="green"
            ))
        except ValueError as e:
            console.print(f"[yellow]{e}[/yellow]")
        return ""

    elif getattr(args, "scan", False):
        console.print(Panel("[bold]Leaders — Scanning all sources[/bold]", border_style="blue"))
        summary = scan_all_leaders(enrich=enrich)
        leaders = load_watchlist()
        report = format_leaders_report(leaders, scan_summary=summary)
        new_count = summary["new_events_found"]
        console.print(Panel(
            f"[green]Scanned {summary['leaders_scanned']} leaders. "
            f"{new_count} new event(s) found.[/green]\n"
            "Report saved to data/leaders_report.md",
            border_style="green"
        ))
        if summary["new_event_urls"]:
            console.print("[bold]New events:[/bold]")
            for url in summary["new_event_urls"]:
                console.print(f"  [cyan]{url}[/cyan]")
        if summary["errors"]:
            for err in summary["errors"]:
                console.print(f"  [yellow]⚠ {err}[/yellow]")
        return report

    else:
        leaders = load_watchlist()
        show_watchlist(leaders)
        return format_leaders_report(leaders)


def run_events(args):
    from skills.event_discovery import run, add_event_from_url

    # --add-url mode: fetch a single URL and add it to the cache
    add_url = getattr(args, "add_url", None)
    if add_url:
        console.print(Panel(f"[bold]Module 2 — Add Event from URL[/bold]\n{add_url}", border_style="blue"))
        event = add_event_from_url(add_url)
        console.print(Panel(
            f"[green]Added: {event.name}\n"
            f"Date: {event.date} | Location: {event.location}\n"
            f"Category: {event.category} | Net Score: {event.net_score}[/green]",
            border_style="green"
        ))
        return f"Added event: {event.name}"

    console.print(Panel("[bold]Module 2 — Event Discovery[/bold]\nScoring networking events in Boston/Cambridge + global strategic forums", border_style="blue"))
    token = os.environ.get("EVENTBRITE_API_TOKEN", "")
    report = run(
        eventbrite_token=token,
        enrich=not getattr(args, "no_enrich", False),
    )
    console.print(Panel("[green]Event report saved to data/events_report.md[/green]", border_style="green"))
    return report


def run_leads(args):
    from skills.lead_generation import run
    console.print(Panel("[bold]Module 3 — Lead Generation[/bold]\nScanning job boards for C-suite and SVP openings", border_style="blue"))
    contacts = getattr(args, "contacts", None)
    apify_key = os.environ.get("APIFY_API_KEY", "")
    report = run(
        contacts_csv=Path(contacts) if contacts else None,
        apify_key=apify_key,
        score=not getattr(args, "no_enrich", False),
    )
    console.print(Panel("[green]Lead report saved to data/leads_report.md[/green]", border_style="green"))
    return report


def run_network(args):
    from skills.network_pathfinder import run
    target = getattr(args, "target", None)
    if not target:
        console.print("[red]Error: --target is required for the network command[/red]")
        sys.exit(1)

    console.print(Panel(f"[bold]Module 4 — Network Pathfinder[/bold]\nFinding paths to: {target}", border_style="blue"))
    contacts = getattr(args, "contacts", None)
    report = run(
        target=target,
        contacts_csv=Path(contacts) if contacts else None,
        target_context=getattr(args, "context", ""),
        jd_snippet=getattr(args, "jd", ""),
        is_company=not getattr(args, "person", False),
        target_person_company=getattr(args, "company", ""),
        generate_scripts=not getattr(args, "no_enrich", False),
    )
    console.print(Panel("[green]Outreach scripts saved to data/outreach_scripts.md[/green]", border_style="green"))
    return report


def run_cv(args):
    from skills.cv_synthesis import run
    jd = getattr(args, "jd", None)
    company = getattr(args, "company", None)
    role = getattr(args, "role", None)

    if not jd:
        console.print("[yellow]Enter job description URL or paste text (end with a blank line):[/yellow]")
        lines = []
        while True:
            try:
                line = input()
                if line == "":
                    break
                lines.append(line)
            except EOFError:
                break
        jd = "\n".join(lines)

    if not company:
        company = console.input("[yellow]Target company name: [/yellow]").strip()
    if not role:
        role = console.input("[yellow]Target role title: [/yellow]").strip()

    console.print(Panel(f"[bold]Module 5 — CV Synthesis[/bold]\nSynthesizing CV for: {role} @ {company}", border_style="blue"))
    result = run(
        jd_input=jd,
        company=company,
        role_title=role,
        output_format=getattr(args, "format", "both"),
    )
    console.print(Panel(f"[green]{result}[/green]", border_style="green"))
    return result


# ── Full Pipeline ─────────────────────────────────────────────────────────────

def run_all(args):
    """Run all 5 modules in dependency order."""
    console.print(Panel(
        "[bold]Job Search Orchestration System[/bold]\nRunning full pipeline: Content → Events → Leads → Network → CV",
        border_style="bold blue"
    ))

    outputs = {}

    # 1. Content Intelligence
    try:
        outputs["content"] = run_content(args)
    except Exception as e:
        console.print(f"[red]Module 1 (Content) failed: {e}[/red]")

    # 2. Event Discovery
    try:
        outputs["events"] = run_events(args)
    except Exception as e:
        console.print(f"[red]Module 2 (Events) failed: {e}[/red]")

    # 3. Lead Generation
    try:
        outputs["leads"] = run_leads(args)
    except Exception as e:
        console.print(f"[red]Module 3 (Leads) failed: {e}[/red]")

    # 4. Network Pathfinder — only if --target provided
    target = getattr(args, "target", None)
    if target:
        try:
            outputs["network"] = run_network(args)
        except Exception as e:
            console.print(f"[red]Module 4 (Network) failed: {e}[/red]")
    else:
        console.print("[yellow]Module 4 (Network): skipped — no --target provided[/yellow]")

    # 5. CV Synthesis — only if --jd, --company, --role all provided
    jd = getattr(args, "jd", None)
    company = getattr(args, "company", None)
    role = getattr(args, "role", None)
    if jd and company and role:
        try:
            outputs["cv"] = run_cv(args)
        except Exception as e:
            console.print(f"[red]Module 5 (CV) failed: {e}[/red]")
    else:
        console.print("[yellow]Module 5 (CV): skipped — provide --jd, --company, --role to include[/yellow]")

    # Write pipeline summary
    _write_summary(outputs)
    console.print(Panel("[bold green]Pipeline complete. Summary saved to data/pipeline_summary.md[/bold green]", border_style="green"))


def run_digest(args):
    """Run event discovery then send the weekly email digest."""
    # 1. Refresh events
    run_events(args)
    # 2. Send email
    from skills.email_digest import run as send_digest
    console.print(Panel("[bold]Email Digest[/bold]\nSending weekly event digest to santiago.aldana@me.com...", border_style="blue"))
    status = send_digest()
    color = "green" if "sent" in status.lower() else "red"
    console.print(Panel(f"[{color}]{status}[/{color}]", border_style=color))
    return status


def run_today(args):
    """Morning brief — reads all JSON data, zero API calls."""
    from skills.dashboard import run as dashboard_run
    return dashboard_run(args)


def run_lamp(args):
    """Build / update the LAMP list — ranked employer consideration set."""
    from skills.lamp_list import run as lamp_run
    console.print(Panel(
        "[bold]LAMP List[/bold]\nRanking target employers by Motivation → Postings → Advocacy",
        border_style="blue"
    ))
    return lamp_run(args)


def run_outreach(args):
    """Generate 6-point emails, TIARA prep, track 3B7 follow-ups."""
    from skills.outreach_tracker import run as outreach_run
    return outreach_run(args)


def run_gmail(args):
    """Dispatch gmail subcommands: auth / scan / review / status."""
    from skills.gmail_monitor import run_auth, run_monitor_cycle, run_review, run_status_gmail
    action = getattr(args, "gmail_action", None)
    if action == "auth":
        run_auth(args)
    elif action == "scan":
        console.print(Panel("[bold]Gmail Monitor[/bold]\nScanning emails + generating follow-up drafts...", border_style="blue"))
        result = run_monitor_cycle(args)
        console.print(Panel(f"[green]{result}[/green]", border_style="green"))
        pending = sum(1 for d in __import__("json").loads(
            (__import__("pathlib").Path(__file__).parent / "data" / "pending_drafts.json").read_text()
        ) if d.get("status") == "pending") if (__import__("pathlib").Path(__file__).parent / "data" / "pending_drafts.json").exists() else 0
        if pending:
            console.print(f"[yellow]{pending} draft(s) ready for review → run: python3 orchestrate.py gmail review[/yellow]")
    elif action == "review":
        run_review(args)
    elif action == "status":
        run_status_gmail(args)
    else:
        console.print("[yellow]Usage: python3 orchestrate.py gmail [auth|scan|review|status][/yellow]")


def run_schedule(args):
    """Dispatch schedule subcommands."""
    from skills.scheduler import (
        install, uninstall, status as sched_status,
        install_gmail, uninstall_gmail,
        install_linkedin, uninstall_linkedin,
    )
    action = getattr(args, "schedule_action", None)
    if action == "install":
        install()
    elif action == "uninstall":
        uninstall()
    elif action == "status":
        sched_status()
    elif action == "install-gmail":
        install_gmail()
    elif action == "uninstall-gmail":
        uninstall_gmail()
    elif action == "install-linkedin":
        install_linkedin()
    elif action == "uninstall-linkedin":
        uninstall_linkedin()
    else:
        console.print("[yellow]Usage: python3 orchestrate.py schedule [install|uninstall|status|install-gmail|uninstall-gmail|install-linkedin|uninstall-linkedin][/yellow]")


def _write_summary(outputs: dict):
    """Aggregate key sections from all module outputs into a single summary file."""
    from skills.shared import DATA_DIR
    lines = [
        "# Job Search Pipeline Summary",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]
    module_names = {
        "content": "Module 1 — Content Intelligence",
        "events": "Module 2 — Event Discovery",
        "leads": "Module 3 — Lead Generation",
        "network": "Module 4 — Network Pathfinder",
        "cv": "Module 5 — CV Synthesis",
    }
    for key, name in module_names.items():
        if key in outputs:
            # Take only first 40 lines of each module output for summary
            excerpt = "\n".join(outputs[key].splitlines()[:40])
            lines += [f"## {name}", "", excerpt, "", "---", ""]
        else:
            lines += [f"## {name}", "_Not run in this pipeline execution._", "", "---", ""]

    summary_path = DATA_DIR / "pipeline_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")


# ── Status Command ────────────────────────────────────────────────────────────

def run_status(args):
    """Print a quick status table of all module outputs and their last run time."""
    from skills.shared import DATA_DIR, CV_OUTPUT_DIR

    output_files = {
        "Module 1 — Content": DATA_DIR / "content_drafts.md",
        "Module 2 — Events": DATA_DIR / "events_report.md",
        "Leaders Watchlist": DATA_DIR / "leaders_report.md",
        "Module 3 — Leads": DATA_DIR / "leads_report.md",
        "Module 4 — Network": DATA_DIR / "outreach_scripts.md",
        "Module 5 — CV Output": CV_OUTPUT_DIR,
    }

    table = Table(title="Job Search System Status", box=box.ROUNDED)
    table.add_column("Module", style="bold")
    table.add_column("Output")
    table.add_column("Last Updated")
    table.add_column("Status")

    for name, path in output_files.items():
        if path.is_dir():
            # CV output dir — check for any PDFs
            files = list(path.glob("*.pdf")) + list(path.glob("*.html"))
            if files:
                latest = max(files, key=lambda f: f.stat().st_mtime)
                mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                table.add_row(name, latest.name, mtime, "[green]✓[/green]")
            else:
                table.add_row(name, str(path.relative_to(BASE_DIR)), "—", "[dim]No output yet[/dim]")
        elif path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size = f"{path.stat().st_size // 1024}KB" if path.stat().st_size > 1024 else f"{path.stat().st_size}B"
            table.add_row(name, path.name, mtime, f"[green]✓[/green] {size}")
        else:
            table.add_row(name, path.name, "—", "[dim]Not run[/dim]")

    console.print(table)

    # Check env vars
    console.print()
    env_table = Table(title="Environment", box=box.SIMPLE)
    env_table.add_column("Key")
    env_table.add_column("Status")
    for key in ["ANTHROPIC_API_KEY", "EVENTBRITE_API_TOKEN", "APIFY_API_KEY"]:
        val = os.environ.get(key, "")
        if val:
            env_table.add_row(key, f"[green]Set ({val[:8]}...)[/green]")
        else:
            status = "[yellow]Optional — not set[/yellow]" if key != "ANTHROPIC_API_KEY" else "[red]REQUIRED — not set[/red]"
            env_table.add_row(key, status)
    console.print(env_table)


def run_server(args):
    from skills.server import run as server_run
    port = getattr(args, "port", 5050)
    console.print(Panel(
        f"[bold]Web Dashboard[/bold]\nStarting at [link]http://localhost:{port}[/link]\nPress Ctrl+C to stop.",
        border_style="cyan"
    ))
    server_run(port=port, open_browser=True)


def run_linkedin(args):
    from skills.linkedin_engine import run as linkedin_run
    return linkedin_run(args)


# ── Argument Parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrate.py",
        description="Job Search Orchestration System — Santiago Aldana",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 orchestrate.py status
  python3 orchestrate.py content --days 14 --drafts 3
  python3 orchestrate.py events --no-enrich
  python3 orchestrate.py leads --contacts cv/contacts_export.csv
  python3 orchestrate.py network --target "Stripe" --contacts cv/contacts_export.csv
  python3 orchestrate.py cv --jd https://stripe.com/jobs/123 --company Stripe --role CPO
  python3 orchestrate.py all --no-enrich --contacts cv/contacts_export.csv
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # ── today ────────────────────────────────────────────────────────────────
    subparsers.add_parser("today", help="Morning brief: actions due, LAMP targets, events (no API)")

    # ── status ──────────────────────────────────────────────────────────────
    subparsers.add_parser("status", help="Show status of all module outputs")

    # ── content ─────────────────────────────────────────────────────────────
    p_content = subparsers.add_parser("content", help="Module 1: Generate LinkedIn post drafts")
    p_content.add_argument("--days", type=int, default=7, help="Article age in days (default: 7)")
    p_content.add_argument("--drafts", type=int, default=5, help="Number of drafts (default: 5)")
    p_content.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                           help="Skip Claude drafting")

    # ── leaders ─────────────────────────────────────────────────────────────
    p_leaders = subparsers.add_parser("leaders", help="Track thought leaders as event/content sources")
    p_leaders.add_argument("--add", metavar="NAME", default=None,
                           help='Add a leader by name: --add "Paul Baier"')
    p_leaders.add_argument("--org", metavar="ORG", default="",
                           help="Organization for --add")
    p_leaders.add_argument("--substack", metavar="URL", default=None,
                           help="Substack URL for --add")
    p_leaders.add_argument("--luma", metavar="URL", default=None,
                           help="Luma profile URL for --add")
    p_leaders.add_argument("--meetup", metavar="URL", default=None,
                           help="Meetup.com group URL for --add")
    p_leaders.add_argument("--website", metavar="URL", default=None,
                           help="Website URL for --add")
    p_leaders.add_argument("--notes", metavar="TEXT", default="",
                           help="Free-text notes for --add")
    p_leaders.add_argument("--topics", metavar="TOPICS", default="",
                           help='Comma-separated topics: --topics "AI,fintech,Boston"')
    p_leaders.add_argument("--scan", action="store_true",
                           help="Scan all leader sources for new events")
    p_leaders.add_argument("--add-url", dest="add_url", metavar="URL", default=None,
                           help='Quick-add by profile URL: --add-url "https://lu.ma/x" --add "Name"')
    p_leaders.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                           help="Skip Claude Haiku classification (use keyword heuristic only)")

    # ── events ──────────────────────────────────────────────────────────────
    p_events = subparsers.add_parser("events", help="Module 2: Discover and score networking events")
    p_events.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                          help="Skip Claude tactical briefs")
    p_events.add_argument("--add-url", dest="add_url", default=None, metavar="URL",
                          help="Fetch a single event URL, score it, and add it to the event list")

    # ── leads ───────────────────────────────────────────────────────────────
    p_leads = subparsers.add_parser("leads", help="Module 3: Discover C-suite job openings")
    p_leads.add_argument("--contacts", type=str, default=None,
                         help="LinkedIn contacts CSV path")
    p_leads.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                         help="Skip Claude scoring (uniform scores)")

    # ── network ─────────────────────────────────────────────────────────────
    p_network = subparsers.add_parser("network", help="Module 4: Map paths to target + generate outreach scripts")
    p_network.add_argument("--target", required=True, help="Target company or person name")
    p_network.add_argument("--contacts", type=str, default=None,
                           help="LinkedIn contacts CSV path")
    p_network.add_argument("--context", default="",
                           help="Free-text description of target and purpose")
    p_network.add_argument("--jd", default="",
                           help="Job description text or URL for outreach context")
    p_network.add_argument("--person", action="store_true",
                           help="Search by person name instead of company")
    p_network.add_argument("--company", default="",
                           help="Company where target person works")
    p_network.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                           help="Skip Claude script generation")

    # ── cv ──────────────────────────────────────────────────────────────────
    p_cv = subparsers.add_parser("cv", help="Module 5: Synthesize tailored CV from master CV + JD")
    p_cv.add_argument("--jd", default=None,
                      help="Job description URL or raw text")
    p_cv.add_argument("--company", default=None,
                      help="Target company name")
    p_cv.add_argument("--role", default=None,
                      help="Target role title")
    p_cv.add_argument("--format", choices=["pdf", "html", "both"], default="both",
                      help="Output format (default: both)")

    # ── all ─────────────────────────────────────────────────────────────────
    p_all = subparsers.add_parser("all", help="Run full pipeline (Modules 1-5)")
    p_all.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                       help="Skip all Claude API calls")
    p_all.add_argument("--contacts", type=str, default=None,
                       help="LinkedIn contacts CSV path")
    p_all.add_argument("--target", default=None,
                       help="Target for Module 4 (optional)")
    p_all.add_argument("--jd", default=None,
                       help="JD for Module 5 (optional)")
    p_all.add_argument("--company", default=None,
                       help="Company for Module 5 (optional)")
    p_all.add_argument("--role", default=None,
                       help="Role for Module 5 (optional)")
    p_all.add_argument("--format", choices=["pdf", "html", "both"], default="both")

    # ── digest ───────────────────────────────────────────────────────────────
    p_digest = subparsers.add_parser("digest", help="Refresh events + send weekly email digest")
    p_digest.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                          help="Skip Claude tactical briefs")

    # ── schedule ─────────────────────────────────────────────────────────────
    p_schedule = subparsers.add_parser("schedule", help="Manage Monday 8am launchd automation")
    sched_sub = p_schedule.add_subparsers(dest="schedule_action")
    sched_sub.add_parser("install",          help="Install launchd job (Monday 8am digest)")
    sched_sub.add_parser("uninstall",        help="Remove digest launchd job")
    sched_sub.add_parser("status",           help="Check if digest scheduler is active")
    sched_sub.add_parser("install-gmail",      help="Install Gmail monitor (every 30 min)")
    sched_sub.add_parser("uninstall-gmail",    help="Remove Gmail monitor launchd job")
    sched_sub.add_parser("install-linkedin",   help="Install LinkedIn publish job (every 30 min)")
    sched_sub.add_parser("uninstall-linkedin", help="Remove LinkedIn publish launchd job")

    # ── lamp ─────────────────────────────────────────────────────────────────
    p_lamp = subparsers.add_parser("lamp", help="Build/manage LAMP list (2-Hour Job Search)")
    p_lamp.add_argument("--set-motivation", dest="set_motivation", default=None, metavar="PAIRS",
                        help="Set motivation scores e.g. \"Stripe:9,Coinbase:8\"")
    p_lamp.add_argument("--set-status", dest="set_status", default=None, metavar="PAIR",
                        help="Update company status e.g. \"Stripe:booster_found\"")

    # ── gmail ─────────────────────────────────────────────────────────────────
    p_gmail = subparsers.add_parser("gmail", help="Monitor Gmail for replies + manage follow-up drafts")
    gmail_sub = p_gmail.add_subparsers(dest="gmail_action")
    gmail_sub.add_parser("auth",   help="Authenticate Gmail accounts (opens browser)")
    gmail_sub.add_parser("scan",   help="Poll Gmail + generate follow-up drafts")
    p_review = gmail_sub.add_parser("review", help="Review/approve/send pending drafts")
    p_review.add_argument("--batch", type=int, default=None, metavar="N",
                          help="Show N drafts at once for bulk approval (e.g. --batch 10)")
    gmail_sub.add_parser("status", help="Show last poll times and pending draft count")

    # ── outreach ─────────────────────────────────────────────────────────────
    p_server = subparsers.add_parser("server", help="Start web dashboard at http://localhost:5050")
    p_server.add_argument("--port", type=int, default=5050, help="Port to listen on (default: 5050)")

    p_out = subparsers.add_parser("outreach", help="6-point emails, TIARA prep, 3B7 tracking")
    p_out.add_argument("--company",  default=None, help="Target company name")
    p_out.add_argument("--contact",  default=None, help="Contact full name")
    p_out.add_argument("--role",     default="",   help="Contact's role title")
    p_out.add_argument("--email",    default="",   help="Contact email address")
    p_out.add_argument("--notes",    default="",   help="Free-text notes about this contact")
    p_out.add_argument("--channel",  default="email",
                       choices=["email", "linkedin_group", "linkedin_connect"],
                       help="Contact channel (default: email)")
    p_out.add_argument("--tiara",    action="store_true",
                       help="Generate TIARA meeting prep instead of email")
    p_out.add_argument("--add",      action="store_true",
                       help="Quick-add a new contact you already emailed (no Claude call)")
    p_out.add_argument("--track",    action="store_true",
                       help="Log a sent outreach (no Claude call)")
    p_out.add_argument("--status",   action="store_true",
                       help="Show due 3B7 actions and all active outreaches")
    p_out.add_argument("--mark-responded", dest="mark_responded", default=None, metavar="COMPANY:NAME",
                       help="Mark a contact as responded e.g. \"Stripe:Jane Smith\"")
    p_out.add_argument("--booster",  action="store_true",
                       help="Used with --mark-responded: classify as booster")
    p_out.add_argument("--referral", default=None, metavar="NAME",
                       help="Referral contact name (used with --mark-responded)")

    # ── linkedin ──────────────────────────────────────────────────────────────
    p_li = subparsers.add_parser("linkedin", help="LinkedIn posts + comments: draft, schedule, publish")
    li_sub = p_li.add_subparsers(dest="linkedin_cmd")
    li_sub.add_parser("auth",    help="One-time OAuth setup (opens browser)")
    li_sub.add_parser("scan",    help="Scrape feed via Apify + import content drafts")
    li_sub.add_parser("draft",   help="Import content drafts only (no scraping)")
    li_sub.add_parser("status",  help="Show pending/scheduled/published counts")
    li_sub.add_parser("publish", help="Publish scheduled items now (called by launchd)")
    p_li_comment = li_sub.add_parser("comment", help="Draft comment for a LinkedIn post URL")
    p_li_comment.add_argument("--url",          required=True, help="LinkedIn post URL to comment on")
    p_li_comment.add_argument("--author",       default="",    help="Author name (if page requires login)")
    p_li_comment.add_argument("--author-title", dest="author_title", default="", help="Author title/role")
    p_li_comment.add_argument("--no-enrich",    action="store_true", dest="no_enrich")
    p_li_post = li_sub.add_parser("post", help="Add a manual original post draft")
    p_li_post.add_argument("--body",       required=True, help="Post text (≤3000 chars)")
    p_li_post.add_argument("--url",        default="",    help="Source article URL (optional)")
    p_li.add_argument("--no-enrich", action="store_true", dest="no_enrich",
                      help="Skip Claude calls")

    return parser


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Check ANTHROPIC_API_KEY for commands that need it
    # lamp never calls Claude; outreach only needs it for email gen / tiara (not --track/--status/--mark-responded)
    # gmail auth/review/status never call Anthropic; gmail scan does only if ANTHROPIC_API_KEY set
    # linkedin auth/status/publish don't need Anthropic key; scan/comment/post do
    linkedin_no_api = (
        args.command == "linkedin" and
        getattr(args, "linkedin_cmd", None) in ("auth", "status", "publish", None)
    )
    no_api_commands = ("status", "today", "schedule", "digest", "lamp", "gmail", "server")
    outreach_no_api = (
        args.command == "outreach" and (
            getattr(args, "track", False) or
            getattr(args, "add", False) or
            getattr(args, "status", False) or
            getattr(args, "mark_responded", None) is not None
        )
    )
    leaders_no_api = (
        args.command == "leaders" and (
            not getattr(args, "scan", False) or getattr(args, "no_enrich", False)
        )
    )
    if args.command not in no_api_commands and not outreach_no_api and not leaders_no_api and not linkedin_no_api and not getattr(args, "no_enrich", False):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            console.print("[red]Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.[/red]")
            console.print("[dim]Run with --no-enrich to skip Claude API calls.[/dim]")
            sys.exit(1)

    dispatch = {
        "today":    run_today,
        "status":   run_status,
        "content":  run_content,
        "events":   run_events,
        "leaders":  run_leaders,
        "leads":    run_leads,
        "network":  run_network,
        "cv":       run_cv,
        "all":      run_all,
        "digest":   run_digest,
        "schedule": run_schedule,
        "lamp":     run_lamp,
        "outreach": run_outreach,
        "gmail":    run_gmail,
        "server":   run_server,
        "linkedin": run_linkedin,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
