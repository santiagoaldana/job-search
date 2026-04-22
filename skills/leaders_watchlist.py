"""
Leader/Influencer Watchlist — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Tracks thought leaders in Boston AI/FinTech as automated event discovery sources.
Scans their Substack RSS feeds, Luma profiles, and Meetup.com groups for event
announcements, then routes discovered URLs through the existing add_event_from_url()
pipeline in event_discovery.py.

Sources per leader (all optional, any combination):
  - substack_url  → RSS feed (/feed or /rss)
  - luma_profile_url → __NEXT_DATA__ JSON or href scraping
  - meetup_url    → public /events/ page scraping

CLI:
  python3 orchestrate.py leaders                          # show watchlist table
  python3 orchestrate.py leaders --scan                   # scan all sources
  python3 orchestrate.py leaders --scan --no-enrich       # keyword heuristic only
  python3 orchestrate.py leaders --add "Name" --org "Org" --substack "url"
  python3 orchestrate.py leaders --add-url "https://lu.ma/x" --add "Name"
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
from bs4 import BeautifulSoup

import anthropic
from skills.shared import DATA_DIR, MODEL_HAIKU, EXECUTIVE_PROFILE

# ── Constants ─────────────────────────────────────────────────────────────────

WATCHLIST_PATH = DATA_DIR / "leaders_watchlist.json"
REPORT_PATH    = DATA_DIR / "leaders_report.md"

EVENT_KEYWORDS = [
    "workshop", "meetup", "conference", "register", "join us", "event",
    "invitation", "summit", "webinar", "demo day", "hackathon", "symposium",
    "fireside", "panel", "networking", "session", "seminar", "bootcamp",
]

SOCIAL_SHARE_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "linkedin.com",
    "instagram.com", "youtube.com", "t.co",
}

SEED_LEADERS = [
    {
        "name": "Paul Baier",
        "organization": "GAI Insights",
        "topics": ["generative AI", "enterprise AI", "AI strategy", "Boston AI"],
        "substack_url": "https://gaiinsights.substack.com",
        "luma_profile_url": None,
        "meetup_url": None,
        "website_url": "https://gaiinsights.com",
        "notes": (
            "Discovered MIT Imagination in Action 2026 via his email. "
            "Active MIT ecosystem connector — spoke at MIT CSAIL March 2026. "
            "Substack RSS confirmed at gaiinsights.substack.com/feed."
        ),
        "added_date": "2026-04-09",
        "last_checked": None,
        "events_found": ["https://imaginationinaction.co/2604mit/workshop"],
    },
    {
        "name": "Judah Phillips",
        "organization": "Boston Generative AI Meetup",
        "topics": ["generative AI", "LLM", "Boston AI"],
        "substack_url": None,
        "luma_profile_url": None,
        "meetup_url": "https://www.meetup.com/boston-generative-ai-meetup/",
        "website_url": "https://aiweek.boston",
        "notes": "Organizer of Boston Generative AI Meetup (Meetup.com) and Boston AI Week.",
        "added_date": "2026-04-09",
        "last_checked": None,
        "events_found": [],
    },
]


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_watchlist() -> list[dict]:
    """Load leaders_watchlist.json. Returns [] if missing or malformed."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text())
    except Exception as e:
        print(f"[Leaders] Warning: could not parse watchlist: {e}")
        return []


def save_watchlist(leaders: list[dict]) -> None:
    """Atomic write to leaders_watchlist.json."""
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = WATCHLIST_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(leaders, indent=2, default=str))
    tmp.replace(WATCHLIST_PATH)


def seed_watchlist() -> None:
    """Create leaders_watchlist.json with default entries if it does not exist."""
    if WATCHLIST_PATH.exists():
        return
    save_watchlist(SEED_LEADERS)
    print(f"[Leaders] Seeded watchlist with {len(SEED_LEADERS)} leaders → {WATCHLIST_PATH}")


# ── Management ────────────────────────────────────────────────────────────────

def add_leader(
    name: str,
    organization: str = "",
    substack_url: str | None = None,
    luma_profile_url: str | None = None,
    meetup_url: str | None = None,
    website_url: str | None = None,
    topics: list[str] | None = None,
    notes: str = "",
) -> dict:
    """
    Append a new leader to the watchlist.
    Raises ValueError if a leader with the same (name, org) already exists.
    """
    leaders = load_watchlist()
    key = (name.strip().lower(), organization.strip().lower())
    for existing in leaders:
        if (existing["name"].lower(), existing.get("organization", "").lower()) == key:
            raise ValueError(f"Leader already in watchlist: {name} ({organization})")

    entry = {
        "name": name.strip(),
        "organization": organization.strip(),
        "topics": topics or [],
        "substack_url": substack_url or None,
        "luma_profile_url": luma_profile_url or None,
        "meetup_url": meetup_url or None,
        "website_url": website_url or None,
        "notes": notes.strip(),
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "last_checked": None,
        "events_found": [],
    }
    leaders.append(entry)
    save_watchlist(leaders)
    print(f"[Leaders] Added: {name} ({organization})")
    return entry


def add_leader_from_url(profile_url: str, name: str) -> dict:
    """
    Infer the platform from the URL and pre-fill the appropriate field.
    lu.ma/* → luma_profile_url
    *.substack.com/* → substack_url
    meetup.com/* → meetup_url
    """
    url_lower = profile_url.lower()
    kwargs: dict = {"name": name}

    if "lu.ma" in url_lower or "luma.com" in url_lower:
        kwargs["luma_profile_url"] = profile_url
    elif "substack.com" in url_lower:
        kwargs["substack_url"] = profile_url
    elif "meetup.com" in url_lower:
        kwargs["meetup_url"] = profile_url
    else:
        kwargs["website_url"] = profile_url

    return add_leader(**kwargs)


# ── Substack Scanning ─────────────────────────────────────────────────────────

def fetch_substack_posts(substack_url: str, max_posts: int = 10) -> list[dict]:
    """
    Fetch recent posts via RSS. Tries /feed then /rss.
    Returns [] on any error — never raises.
    """
    base = substack_url.rstrip("/")
    for suffix in ["/feed", "/rss"]:
        feed_url = base + suffix
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                print(f"[Leaders] Substack feed malformed ({feed_url}): {feed.bozo_exception}")
                continue
            posts = []
            for entry in feed.entries[:max_posts]:
                posts.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "") or entry.get("content", [{}])[0].get("value", ""),
                })
            if posts:
                print(f"[Leaders] Substack {base}: {len(posts)} posts fetched")
                return posts
        except Exception as e:
            print(f"[Leaders] Error fetching {feed_url}: {e}")
    print(f"[Leaders] No posts found for {substack_url}")
    return []


def classify_posts_for_events(posts: list[dict], enrich: bool = True) -> list[dict]:
    """
    Identify posts that announce events.
    enrich=True: uses MODEL_HAIKU (batch, ≤10 posts/call).
    enrich=False or no API key: keyword heuristic on title+summary.
    Returns only event-bearing posts.
    """
    if not posts:
        return []

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if enrich and has_api_key:
        try:
            client = anthropic.Anthropic()
            batch = posts[:10]
            items = "\n".join(
                f"{i+1}. TITLE: {p['title']}\nSUMMARY: {p['summary'][:300]}"
                for i, p in enumerate(batch)
            )
            prompt = f"""You are reviewing Substack posts from Boston AI/FinTech thought leaders.
Identify which posts announce or mention an upcoming in-person or virtual event
(workshop, meetup, conference, summit, demo day, panel, webinar, etc.).

Posts to review:
{items}

Return a JSON array of booleans (true/false), one per post in order.
Example for 3 posts: [true, false, true]
Return ONLY the JSON array, no other text."""

            response = client.messages.create(
                model=MODEL_HAIKU,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            flags = json.loads(raw)
            result = [p for p, flag in zip(batch, flags) if flag]
            print(f"[Leaders] Haiku classified {len(result)}/{len(batch)} posts as event-bearing")
            return result
        except Exception as e:
            print(f"[Leaders] Haiku classification failed, falling back to keywords: {e}")

    # Keyword heuristic fallback
    result = []
    for post in posts:
        text = (post["title"] + " " + post["summary"]).lower()
        if any(kw in text for kw in EVENT_KEYWORDS):
            result.append(post)
    print(f"[Leaders] Keyword heuristic: {len(result)}/{len(posts)} posts matched")
    return result


def extract_event_urls(posts: list[dict], already_seen: set[str]) -> list[str]:
    """
    Extract candidate event URLs from event-bearing posts.
    Filters social share links, post's own URL, and already_seen.
    """
    candidates: list[str] = []
    seen_in_this_call: set[str] = set()

    for post in posts:
        post_own_url = post.get("url", "")
        summary_html = post.get("summary", "")

        # Parse hrefs from summary HTML
        try:
            soup = BeautifulSoup(summary_html, "html.parser")
            hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
        except Exception:
            hrefs = []

        # Bare URLs from text
        text = BeautifulSoup(summary_html, "html.parser").get_text()
        bare = re.findall(r'https?://\S+', text)

        for url in hrefs + bare:
            url = url.rstrip(".,;)")
            if not url.startswith("http"):
                continue
            if url in already_seen or url in seen_in_this_call:
                continue
            if url == post_own_url:
                continue
            domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
            if domain in SOCIAL_SHARE_DOMAINS:
                continue
            seen_in_this_call.add(url)
            candidates.append(url)

    return candidates


# ── Luma Profile Scanning ─────────────────────────────────────────────────────

def fetch_luma_profile_events(luma_profile_url: str) -> list[str]:
    """
    Extract event URLs from a Luma profile page.
    Tries __NEXT_DATA__ JSON first; falls back to href scraping.
    Returns [] on any error.
    """
    try:
        resp = httpx.get(
            luma_profile_url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code != 200:
            print(f"[Leaders] Luma profile HTTP {resp.status_code}: {luma_profile_url}")
            return []

        # Try __NEXT_DATA__ JSON
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text, re.DOTALL
        )
        if match:
            try:
                data = json.loads(match.group(1))
                events_data = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("initialData", {})
                        .get("data", {})
                )
                raw_events = events_data.get("events", []) + events_data.get("featured_events", [])
                urls = []
                for raw in raw_events:
                    ev = raw.get("event", raw)
                    slug = ev.get("url", ev.get("slug", ""))
                    if slug:
                        url = f"https://lu.ma/{slug}" if not slug.startswith("http") else slug
                        urls.append(url)
                if urls:
                    print(f"[Leaders] Luma profile: {len(urls)} events via __NEXT_DATA__")
                    return urls
            except Exception:
                pass

        # Fallback: href scraping for lu.ma/[slug] links
        soup = BeautifulSoup(resp.text, "html.parser")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r'^https?://lu\.ma/[^/]+$', href) or re.match(r'^/[^/]+$', href):
                full = href if href.startswith("http") else f"https://lu.ma{href}"
                # Skip profile/community links
                if not any(x in full for x in ["/c/", "/user/", "/calendar"]):
                    urls.append(full)
        urls = list(dict.fromkeys(urls))  # dedupe, preserve order
        print(f"[Leaders] Luma profile: {len(urls)} events via href scraping")
        return urls

    except Exception as e:
        print(f"[Leaders] Error fetching Luma profile {luma_profile_url}: {e}")
        return []


# ── Meetup.com Scanning ───────────────────────────────────────────────────────

def fetch_meetup_events(meetup_url: str) -> list[str]:
    """
    Scrape upcoming events from a public Meetup.com group page.
    Targets the /events/ listing — no auth required.
    Returns [] on any error.
    """
    base = meetup_url.rstrip("/")
    events_url = base + "/events/"
    try:
        resp = httpx.get(
            events_url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code != 200:
            print(f"[Leaders] Meetup HTTP {resp.status_code}: {events_url}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        urls = []
        group_slug = base.split("meetup.com/")[-1].strip("/")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Match /group-name/events/12345678/ pattern
            if re.search(r'/events/\d+', href):
                if href.startswith("http"):
                    full = href.split("?")[0]
                else:
                    full = "https://www.meetup.com" + href.split("?")[0]
                urls.append(full)

        urls = list(dict.fromkeys(urls))
        print(f"[Leaders] Meetup {group_slug}: {len(urls)} event URLs found")
        return urls

    except Exception as e:
        print(f"[Leaders] Error fetching Meetup {meetup_url}: {e}")
        return []


# ── Main Scan ─────────────────────────────────────────────────────────────────

def scan_all_leaders(enrich: bool = True) -> dict:
    """
    Scan all leaders in the watchlist for new event URLs.
    Discovered URLs are routed through add_event_from_url() from event_discovery.py.

    Returns summary: {leaders_scanned, new_events_found, new_event_urls, errors}
    """
    from skills.event_discovery import add_event_from_url, CACHE_PATH

    leaders = load_watchlist()
    if not leaders:
        print("[Leaders] Watchlist is empty. Run `leaders --add` to add leaders.")
        return {"leaders_scanned": 0, "new_events_found": 0, "new_event_urls": [], "errors": []}

    # Build global dedup set from existing events cache
    seen_globally: set[str] = set()
    if CACHE_PATH.exists():
        try:
            existing = json.loads(CACHE_PATH.read_text())
            seen_globally = {e.get("url", "") for e in existing if e.get("url")}
        except Exception:
            pass

    summary = {
        "leaders_scanned": 0,
        "new_events_found": 0,
        "new_event_urls": [],
        "errors": [],
    }

    for i, leader in enumerate(leaders):
        name = leader["name"]
        print(f"\n[Leaders] Scanning {i+1}/{len(leaders)}: {name}")

        # Also skip URLs already recorded for this leader
        leader_seen: set[str] = seen_globally | set(leader.get("events_found", []))

        candidate_urls: list[str] = []

        # Substack
        if leader.get("substack_url"):
            posts = fetch_substack_posts(leader["substack_url"])
            event_posts = classify_posts_for_events(posts, enrich=enrich)
            substack_urls = extract_event_urls(event_posts, leader_seen)
            candidate_urls.extend(substack_urls)

        # Luma profile
        if leader.get("luma_profile_url"):
            luma_urls = fetch_luma_profile_events(leader["luma_profile_url"])
            candidate_urls.extend(u for u in luma_urls if u not in leader_seen)

        # Meetup.com
        if leader.get("meetup_url"):
            meetup_urls = fetch_meetup_events(leader["meetup_url"])
            candidate_urls.extend(u for u in meetup_urls if u not in leader_seen)

        # Dedupe candidates
        candidate_urls = list(dict.fromkeys(candidate_urls))
        new_for_leader: list[str] = []

        for url in candidate_urls:
            if url in seen_globally:
                continue
            print(f"[Leaders]   → Processing: {url}")
            try:
                add_event_from_url(url)
                new_for_leader.append(url)
                seen_globally.add(url)
                summary["new_events_found"] += 1
                summary["new_event_urls"].append(url)
            except Exception as e:
                msg = f"{name}: {url} — {e}"
                print(f"[Leaders]   ✗ Failed: {msg}")
                summary["errors"].append(msg)

        # Update leader record
        leader["last_checked"] = datetime.now().strftime("%Y-%m-%d")
        leader["events_found"] = list(dict.fromkeys(
            leader.get("events_found", []) + new_for_leader
        ))
        leader_seen |= set(new_for_leader)

        summary["leaders_scanned"] += 1

        # Save after each leader (resilient to interruption)
        save_watchlist(leaders)

        # Polite delay between leaders
        if i < len(leaders) - 1:
            time.sleep(1)

    print(f"\n[Leaders] Scan complete: {summary['new_events_found']} new event(s) across {summary['leaders_scanned']} leaders")
    return summary


# ── Reporting ─────────────────────────────────────────────────────────────────

def format_leaders_report(leaders: list[dict], scan_summary: dict | None = None) -> str:
    """Generate leaders_report.md and return as string."""
    lines = [
        "# Leader Watchlist Report",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ",
        f"_Leaders tracked: {len(leaders)}_",
        "",
    ]

    for leader in leaders:
        sources = []
        if leader.get("substack_url"):
            sources.append(f"Substack: {leader['substack_url']}")
        if leader.get("luma_profile_url"):
            sources.append(f"Luma: {leader['luma_profile_url']}")
        if leader.get("meetup_url"):
            sources.append(f"Meetup: {leader['meetup_url']}")
        if leader.get("website_url"):
            sources.append(f"Website: {leader['website_url']}")

        events = leader.get("events_found", [])
        last_checked = leader.get("last_checked") or "Never"

        lines += [
            f"## {leader['name']} — {leader.get('organization', '')}",
            f"- **Topics**: {', '.join(leader.get('topics', []))}",
            f"- **Sources**: {' | '.join(sources) if sources else 'None configured'}",
            f"- **Last checked**: {last_checked}",
            f"- **Notes**: {leader.get('notes', '')}",
            f"- **Events found ({len(events)})**:",
        ]
        for url in events:
            lines.append(f"  - {url}")
        lines.append("\n---")

    if scan_summary and scan_summary.get("new_event_urls"):
        lines += [
            "",
            "## New This Scan",
        ]
        for url in scan_summary["new_event_urls"]:
            lines.append(f"- {url}")
        if scan_summary.get("errors"):
            lines += ["", "**Errors:**"]
            for err in scan_summary["errors"]:
                lines.append(f"- {err}")

    report = "\n".join(lines)
    REPORT_PATH.write_text(report)
    return report


def show_watchlist(leaders: list[dict]) -> None:
    """Print a rich.Table summary of the watchlist."""
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    table = Table(title="Leader Watchlist", box=box.ROUNDED)
    table.add_column("Name", style="bold")
    table.add_column("Organization")
    table.add_column("Substack")
    table.add_column("Luma")
    table.add_column("Meetup")
    table.add_column("Last Checked")
    table.add_column("Events Found", justify="right")

    for leader in leaders:
        table.add_row(
            leader["name"],
            leader.get("organization", ""),
            "[green]✓[/green]" if leader.get("substack_url") else "[dim]—[/dim]",
            "[green]✓[/green]" if leader.get("luma_profile_url") else "[dim]—[/dim]",
            "[green]✓[/green]" if leader.get("meetup_url") else "[dim]—[/dim]",
            leader.get("last_checked") or "[dim]Never[/dim]",
            str(len(leader.get("events_found", []))),
        )

    console.print(table)
    if not leaders:
        console.print("[yellow]Watchlist is empty. Use --add to add leaders.[/yellow]")


# ── Entry Point ───────────────────────────────────────────────────────────────

def run(action: str = "show", enrich: bool = True, add_kwargs: dict | None = None) -> str:
    """Main entry point called by orchestrate.py."""
    seed_watchlist()

    if action == "scan":
        summary = scan_all_leaders(enrich=enrich)
        leaders = load_watchlist()
        return format_leaders_report(leaders, scan_summary=summary)
    elif action == "add" and add_kwargs:
        add_leader(**add_kwargs)
        leaders = load_watchlist()
        return format_leaders_report(leaders)
    elif action == "add-url" and add_kwargs:
        add_leader_from_url(
            profile_url=add_kwargs.pop("profile_url"),
            name=add_kwargs.pop("name"),
        )
        leaders = load_watchlist()
        return format_leaders_report(leaders)
    else:
        leaders = load_watchlist()
        show_watchlist(leaders)
        return format_leaders_report(leaders)
