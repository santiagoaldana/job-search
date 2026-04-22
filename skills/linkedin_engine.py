"""
LinkedIn Engagement Engine — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Manages LinkedIn content creation, scheduling, and publishing:
  - OAuth2 authentication (w_member_social scope)
  - Apify feed scraping for posts to comment on
  - Manual URL submission for targeted comments
  - Claude Opus comment/post drafting
  - Optimal scheduling (Wed/Thu 3–5 PM ET)
  - LinkedIn API publishing (posts + comments)
  - launchd-compatible publish cycle

Usage (via orchestrate.py):
  python3 orchestrate.py linkedin auth           # One-time OAuth setup
  python3 orchestrate.py linkedin scan           # Scrape feed + generate comment drafts
  python3 orchestrate.py linkedin draft          # Import content_cache + generate comments
  python3 orchestrate.py linkedin status         # Show pending/scheduled/published counts
  python3 orchestrate.py linkedin publish        # Publish scheduled items (called by launchd)
"""

import json
import os
import re
import secrets
import threading
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from skills.shared import DATA_DIR, EXECUTIVE_PROFILE, MODEL_HAIKU, MODEL_OPUS

console = Console()

# ── Constants ─────────────────────────────────────────────────────────────────

TOKEN_DIR  = Path.home() / ".job-search-linkedin"
TOKEN_FILE = TOKEN_DIR / "token.json"
DRAFTS_FILE = DATA_DIR / "linkedin_drafts.json"
FEED_CACHE  = DATA_DIR / "linkedin_feed_cache.json"

LINKEDIN_AUTH_URL  = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_API_BASE  = "https://api.linkedin.com/rest"
LINKEDIN_SCOPES    = ["w_member_social", "r_liteprofile", "openid", "profile"]

OAUTH_REDIRECT_PORT = 8765
OAUTH_REDIRECT_URI  = f"http://localhost:{OAUTH_REDIRECT_PORT}/callback"

# Topics for relevance filtering
COMMENT_TOPICS = [
    "fintech", "agentic ai", "agentic commerce", "embedded banking",
    "payments", "digital identity", "fraud prevention", "open banking",
    "stablecoins", "latam", "ai", "credit union", "financial services",
    "insurtech", "regtech", "mvno", "telco", "neobank", "crypto",
    "blockchain", "machine learning", "llm",
]

# Best posting times: Wednesday or Thursday, 3–5 PM ET
OPTIMAL_DAYS   = {2, 3}  # Monday=0 … Sunday=6; Wed=2, Thu=3
OPTIMAL_HOUR_START = 15  # 3 PM ET
OPTIMAL_HOUR_END   = 17  # 5 PM ET

ET_OFFSET = timezone(timedelta(hours=-4))  # EDT (Apr–Oct); close enough


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class LinkedInDraftPost:
    draft_id: str
    type: str                    # "post" | "comment"
    status: str                  # "pending" | "scheduled" | "published" | "discarded"

    # Original post fields
    body: str = ""               # post body text (≤3000 chars)
    source_article_url: str = ""
    source_article_title: str = ""
    controversy_potential: int = 0
    credibility_risk: int = 0
    net_score: float = 0.0
    positioning_angle: str = ""

    # Comment-specific fields
    target_post_url: str = ""    # LinkedIn post URL being commented on
    target_post_author: str = ""
    target_post_author_title: str = ""
    target_post_snippet: str = "" # First 300 chars of the post being commented on
    comment_body: str = ""        # Proposed comment (≤150 words)
    quality_score: int = 0
    relevance_score: int = 0

    # Scheduling
    scheduled_time: str = ""     # ISO datetime (ET) — next Wed/Thu 3–5 PM slot
    created_at: str = ""
    published_at: str = ""
    linkedin_post_id: str = ""


# ── Persistence ───────────────────────────────────────────────────────────────

def load_drafts() -> list[LinkedInDraftPost]:
    if not DRAFTS_FILE.exists():
        return []
    try:
        raw = json.loads(DRAFTS_FILE.read_text(encoding="utf-8"))
        return [LinkedInDraftPost(**d) for d in raw]
    except Exception:
        return []


def save_drafts(drafts: list[LinkedInDraftPost]) -> None:
    tmp = DRAFTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(d) for d in drafts], indent=2), encoding="utf-8")
    tmp.replace(DRAFTS_FILE)


def load_token() -> Optional[dict]:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_token(token: dict) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token, indent=2), encoding="utf-8")


# ── OAuth Authentication ───────────────────────────────────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler to capture the OAuth callback code."""
    auth_code = None
    state_received = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            _OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
            _OAuthCallbackHandler.state_received = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:40px;background:#0f1117;color:#e2e8f0">
<h2 style="color:#22c55e">LinkedIn Connected!</h2>
<p>You can close this tab and return to the terminal.</p>
</body></html>""")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Suppress server logs


def authenticate_linkedin() -> dict:
    """
    OAuth2 Authorization Code flow for LinkedIn.
    Opens browser for user consent, captures code via local callback server.
    Stores token at ~/.job-search-linkedin/token.json.
    Returns the token dict.
    """
    client_id     = os.environ.get("LINKEDIN_CLIENT_ID", "")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        console.print("[red]LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set in .env[/red]")
        console.print("\n[bold]One-time setup:[/bold]")
        console.print("1. Go to https://www.linkedin.com/developers/apps/new")
        console.print("2. Create app: 'Job Search Assistant'")
        console.print("3. Add product: 'Share on LinkedIn' (for w_member_social scope)")
        console.print(f"4. Set Redirect URI: {OAUTH_REDIRECT_URI}")
        console.print("5. Add to .env: LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=...")
        raise RuntimeError("LinkedIn credentials not configured")

    # Check if we already have a valid token
    existing = load_token()
    if existing:
        expiry_str = existing.get("expires_at", "")
        if expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if expiry > datetime.now():
                    console.print(f"[green]Token already valid — expires {expiry.strftime('%Y-%m-%d')}[/green]")
                    return existing
            except ValueError:
                pass

    # Generate CSRF state
    state = secrets.token_urlsafe(16)

    # Build auth URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "state": state,
        "scope": " ".join(LINKEDIN_SCOPES),
    }
    auth_url = f"{LINKEDIN_AUTH_URL}?{urlencode(auth_params)}"

    console.print(Panel(
        f"[bold]LinkedIn OAuth Setup[/bold]\n\n"
        f"Opening browser for LinkedIn authorization...\n\n"
        f"If browser doesn't open, visit:\n[cyan]{auth_url}[/cyan]",
        border_style="blue"
    ))

    # Start local callback server in background
    _OAuthCallbackHandler.auth_code = None
    server = HTTPServer(("localhost", OAUTH_REDIRECT_PORT), _OAuthCallbackHandler)

    def _serve():
        server.handle_request()  # Handle exactly one request

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    webbrowser.open(auth_url)
    console.print("[dim]Waiting for LinkedIn authorization...[/dim]")
    t.join(timeout=120)

    code = _OAuthCallbackHandler.auth_code
    state_received = _OAuthCallbackHandler.state_received

    if not code:
        raise RuntimeError("OAuth timed out or was cancelled — no authorization code received")
    if state_received != state:
        raise RuntimeError("CSRF state mismatch — possible tampering, aborting")

    # Exchange code for token
    with httpx.Client() as client:
        resp = client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  OAUTH_REDIRECT_URI,
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        token_data = resp.json()

    # Fetch member profile (person URN needed for posting)
    with httpx.Client() as client:
        profile_resp = client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()

    # Persist token with expiry and person URN
    expires_in = token_data.get("expires_in", 5183944)  # ~60 days default
    token = {
        "access_token":  token_data["access_token"],
        "expires_at":    (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
        "person_id":     profile.get("sub", ""),
        "person_name":   profile.get("name", ""),
        "person_urn":    f"urn:li:person:{profile.get('sub', '')}",
        "scope":         token_data.get("scope", ""),
    }
    save_token(token)

    console.print(Panel(
        f"[bold green]LinkedIn connected![/bold green]\n\n"
        f"Account    : {token['person_name']}\n"
        f"Person URN : {token['person_urn']}\n"
        f"Expires    : {datetime.fromisoformat(token['expires_at']).strftime('%Y-%m-%d')}\n"
        f"Token file : {TOKEN_FILE}",
        border_style="green",
        title="LinkedIn Auth"
    ))
    return token


def _get_valid_token() -> dict:
    """Load token, check expiry. Raises if not authenticated or expired."""
    token = load_token()
    if not token:
        raise RuntimeError(
            "Not authenticated. Run: python3 orchestrate.py linkedin auth"
        )
    expiry_str = token.get("expires_at", "")
    if expiry_str:
        try:
            if datetime.fromisoformat(expiry_str) <= datetime.now():
                raise RuntimeError(
                    "LinkedIn token expired. Run: python3 orchestrate.py linkedin auth"
                )
        except ValueError:
            pass
    return token


# ── Scheduling ────────────────────────────────────────────────────────────────

def next_optimal_slot(base: Optional[datetime] = None) -> datetime:
    """
    Return the next Wed or Thu between 3–5 PM ET.
    Randomizes minutes within the window to avoid bot-like patterns.
    If today is Wed/Thu and it's before 4:30 PM ET, returns today's slot.
    """
    import random
    now_et = (base or datetime.now()).astimezone(ET_OFFSET)

    # Random minute offset within window (0–119 minutes = 2 hours)
    offset_minutes = random.randint(0, 119)
    slot_hour   = OPTIMAL_HOUR_START + offset_minutes // 60
    slot_minute = offset_minutes % 60

    # Check today first
    if now_et.weekday() in OPTIMAL_DAYS:
        candidate = now_et.replace(hour=slot_hour, minute=slot_minute, second=0, microsecond=0)
        if candidate > now_et + timedelta(minutes=30):  # at least 30 min from now
            return candidate

    # Find next Wed or Thu
    days_ahead = 1
    while days_ahead <= 8:
        candidate_day = now_et + timedelta(days=days_ahead)
        if candidate_day.weekday() in OPTIMAL_DAYS:
            return candidate_day.replace(hour=slot_hour, minute=slot_minute, second=0, microsecond=0)
        days_ahead += 1

    # Fallback: 3 days from now at 4 PM ET
    return (now_et + timedelta(days=3)).replace(hour=16, minute=0, second=0, microsecond=0)


# ── Feed Scraping (Apify) ─────────────────────────────────────────────────────

def scrape_linkedin_feed(apify_key: str, max_posts: int = 30) -> list[dict]:
    """
    Scrape LinkedIn posts via Apify LinkedIn Post Search Scraper actor.
    Returns list of {url, author, author_title, text, likes, comments_count, published_at}.
    """
    actor_id = "curious_coder/linkedin-post-search-scraper"
    run_url  = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"

    search_queries = [
        "fintech payments 2026",
        "agentic AI commerce",
        "embedded banking financial services",
        "digital identity fraud prevention",
        "open banking stablecoins",
    ]

    posts = []
    seen_urls = set()

    with httpx.Client(timeout=120) as client:
        for query in search_queries:
            try:
                resp = client.post(
                    run_url,
                    params={"token": apify_key},
                    json={
                        "searchQueries": [query],
                        "maxResults": max_posts // len(search_queries) + 2,
                        "sortBy": "date_posted",
                    },
                )
                if resp.status_code != 200:
                    console.print(f"[yellow]Apify query '{query}' returned {resp.status_code}[/yellow]")
                    continue
                items = resp.json()
                for item in items:
                    url = item.get("postUrl") or item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    posts.append({
                        "url":          url,
                        "author":       item.get("authorName") or item.get("author", "Unknown"),
                        "author_title": item.get("authorHeadline") or item.get("authorTitle", ""),
                        "text":         (item.get("text") or item.get("content", ""))[:2000],
                        "likes":        item.get("likeCount") or item.get("likes", 0),
                        "comments_count": item.get("commentCount") or item.get("commentsCount", 0),
                        "published_at": item.get("postedDate") or item.get("publishedAt", ""),
                    })
            except Exception as e:
                console.print(f"[yellow]Apify error for '{query}': {e}[/yellow]")

    # Cache results
    tmp = FEED_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(posts, indent=2), encoding="utf-8")
    tmp.replace(FEED_CACHE)

    console.print(f"[dim]Feed cache: {len(posts)} posts saved to {FEED_CACHE.name}[/dim]")
    return posts


def _filter_relevant_posts(posts: list[dict]) -> list[dict]:
    """Keyword filter: keep posts mentioning at least one COMMENT_TOPICS term."""
    relevant = []
    for p in posts:
        text = (p.get("text", "") + " " + p.get("author_title", "")).lower()
        if any(topic in text for topic in COMMENT_TOPICS):
            relevant.append(p)
    return relevant


# ── Comment Drafting (Claude Opus) ────────────────────────────────────────────

COMMENT_PROMPT = """You are drafting a LinkedIn comment on behalf of Santiago Aldana.

Executive profile:
{profile}

POST AUTHOR: {author} ({author_title})
POST TEXT:
{post_text}

Write a LinkedIn comment that:
1. Opens with a specific, non-obvious observation or respectful pushback — NEVER "Great post!" or "Well said!"
2. References ONE concrete, specific Santiago credential that is directly relevant to this post's topic (e.g. "When I scaled SoyYo to 3M users we saw exactly this..." or "Running Avianca's digital transformation, the same bottleneck emerged...")
3. Ends with a pointed, specific question or provocation that invites the author to reply
4. Is 2–4 sentences, strictly ≤150 words
5. Sounds like a senior practitioner, not a consultant or fan
6. Never mentions "job search", "looking for opportunities", or anything self-promotional beyond the credential

Return ONLY valid JSON (no markdown, no backticks):
{{"comment": "...", "quality_score": <1-10>, "relevance_score": <1-10>, "reasoning": "one sentence"}}"""


def draft_comment_for_post(post: dict) -> Optional[LinkedInDraftPost]:
    """Draft a comment for a single LinkedIn post using Claude Opus."""
    import anthropic
    client = anthropic.Anthropic()

    post_text = post.get("text", "")
    author    = post.get("author", "Unknown")
    author_title = post.get("author_title", "")

    prompt = COMMENT_PROMPT.format(
        profile=EXECUTIVE_PROFILE,
        author=author,
        author_title=author_title,
        post_text=post_text[:1500],
    )

    try:
        msg = client.messages.create(
            model=MODEL_OPUS,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
    except Exception as e:
        console.print(f"[yellow]Comment draft failed for {author}: {e}[/yellow]")
        return None

    quality = data.get("quality_score", 0)
    if quality < 7:
        return None  # Below quality threshold

    return LinkedInDraftPost(
        draft_id=str(uuid.uuid4()),
        type="comment",
        status="pending",
        target_post_url=post.get("url", ""),
        target_post_author=author,
        target_post_author_title=author_title,
        target_post_snippet=post_text[:300],
        comment_body=data.get("comment", ""),
        quality_score=quality,
        relevance_score=data.get("relevance_score", 0),
        scheduled_time=next_optimal_slot().isoformat(),
        created_at=datetime.now().isoformat(),
    )


def draft_comments_batch(posts: list[dict], n: int = 10) -> list[LinkedInDraftPost]:
    """Generate comment drafts for the top-n most relevant posts."""
    relevant = _filter_relevant_posts(posts)
    # Prioritize posts with more engagement
    relevant.sort(key=lambda p: (p.get("likes", 0) + p.get("comments_count", 0) * 2), reverse=True)

    drafts = []
    existing_drafts = load_drafts()
    existing_urls = {d.target_post_url for d in existing_drafts if d.type == "comment"}

    for post in relevant[:n * 2]:  # Try up to 2x target to hit n quality drafts
        if post.get("url") in existing_urls:
            continue  # Already drafted for this post
        if len(drafts) >= n:
            break
        console.print(f"  [dim]Drafting comment for {post.get('author','?')}...[/dim]")
        draft = draft_comment_for_post(post)
        if draft:
            drafts.append(draft)

    return drafts


# ── Import Existing Content Drafts ────────────────────────────────────────────

def import_content_drafts() -> list[LinkedInDraftPost]:
    """
    Import original post drafts from content_cache.json (Module 1 output).
    Converts LinkedInDraft objects to LinkedInDraftPost with type='post'.
    Skips posts already in linkedin_drafts.json.
    """
    cache_path = DATA_DIR / "content_cache.json"
    if not cache_path.exists():
        return []

    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    existing_drafts = load_drafts()
    existing_urls = {d.source_article_url for d in existing_drafts if d.type == "post"}

    new_drafts = []
    for item in raw:
        url = item.get("article_url", "")
        if url in existing_urls:
            continue
        new_drafts.append(LinkedInDraftPost(
            draft_id=str(uuid.uuid4()),
            type="post",
            status="pending",
            body=item.get("draft_text", ""),
            source_article_url=url,
            source_article_title=item.get("article_title", ""),
            controversy_potential=item.get("controversy_potential", 0),
            credibility_risk=item.get("credibility_risk", 0),
            net_score=item.get("net_score", 0.0),
            positioning_angle=item.get("positioning_angle", ""),
            scheduled_time=next_optimal_slot().isoformat(),
            created_at=datetime.now().isoformat(),
        ))

    return new_drafts


# ── Manual Entry Points ───────────────────────────────────────────────────────

def add_manual_post(body: str, source_url: str = "") -> LinkedInDraftPost:
    """Create a pending post draft from manually written text."""
    draft = LinkedInDraftPost(
        draft_id=str(uuid.uuid4()),
        type="post",
        status="pending",
        body=body,
        source_article_url=source_url,
        scheduled_time=next_optimal_slot().isoformat(),
        created_at=datetime.now().isoformat(),
    )
    drafts = load_drafts()
    drafts.append(draft)
    save_drafts(drafts)
    return draft


def add_manual_comment_from_url(target_url: str, author: str = "", author_title: str = "") -> Optional[LinkedInDraftPost]:
    """
    Fetch a LinkedIn post URL and generate a comment draft.
    Uses httpx + BeautifulSoup to extract post text.
    """
    import anthropic

    console.print(f"[dim]Fetching post: {target_url}[/dim]")

    post_text = ""
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }) as client:
            resp = client.get(target_url)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                # Try multiple selectors for LinkedIn post text
                for sel in [
                    "div.attributed-text-segment-list__content",
                    "div.feed-shared-update-v2__description",
                    "div.update-components-text",
                    "span.break-words",
                ]:
                    el = soup.select_one(sel)
                    if el:
                        post_text = el.get_text(separator=" ", strip=True)[:2000]
                        break
                if not post_text:
                    # Fallback: grab og:description meta tag
                    og = soup.find("meta", property="og:description")
                    if og:
                        post_text = og.get("content", "")[:2000]
    except Exception as e:
        console.print(f"[yellow]Could not fetch post text: {e}[/yellow]")

    if not post_text and not author:
        console.print("[yellow]Could not extract post text. Provide --author and paste text manually.[/yellow]")
        return None

    post = {
        "url":          target_url,
        "author":       author or "LinkedIn contact",
        "author_title": author_title,
        "text":         post_text or f"[Post at {target_url}]",
    }

    draft = draft_comment_for_post(post)
    if draft:
        drafts = load_drafts()
        drafts.append(draft)
        save_drafts(drafts)
    return draft


# ── Publishing ────────────────────────────────────────────────────────────────

def _linkedin_headers(access_token: str) -> dict:
    return {
        "Authorization":   f"Bearer {access_token}",
        "Content-Type":    "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
    }


def publish_post(draft: LinkedInDraftPost, token: dict) -> str:
    """
    Publish an original post to LinkedIn.
    Returns the LinkedIn post ID on success.
    """
    person_urn = token.get("person_urn", "")
    if not person_urn:
        raise RuntimeError("person_urn not in token — re-authenticate")

    payload = {
        "author":         person_urn,
        "commentary":     draft.body,
        "visibility":     "PUBLIC",
        "lifecycleState": "PUBLISHED",
        "distribution":   {
            "feedDistribution": "MAIN_FEED",
            "targetEntities":   [],
            "thirdPartyDistributionChannels": [],
        },
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{LINKEDIN_API_BASE}/posts",
            headers=_linkedin_headers(token["access_token"]),
            json=payload,
        )
        resp.raise_for_status()

    # LinkedIn returns the post ID in the X-RestLi-Id header
    post_id = resp.headers.get("x-restli-id", resp.headers.get("X-RestLi-Id", ""))
    return post_id


def _extract_post_urn(post_url: str) -> Optional[str]:
    """
    Extract the LinkedIn post URN from a share URL.
    Handles formats like:
      https://www.linkedin.com/posts/person-name_topic_activity-7123456789-abcd
      https://www.linkedin.com/feed/update/urn:li:activity:7123456789
    """
    # Format 1: urn in URL directly
    urn_match = re.search(r"urn:li:activity:(\d+)", post_url)
    if urn_match:
        return f"urn:li:activity:{urn_match.group(1)}"

    # Format 2: activity ID at end of posts URL
    activity_match = re.search(r"activity-(\d+)", post_url)
    if activity_match:
        return f"urn:li:activity:{activity_match.group(1)}"

    return None


def publish_comment(draft: LinkedInDraftPost, token: dict) -> str:
    """
    Publish a comment on a LinkedIn post.
    Returns the comment ID on success.
    """
    person_urn = token.get("person_urn", "")
    post_urn   = _extract_post_urn(draft.target_post_url)

    if not post_urn:
        raise RuntimeError(
            f"Could not extract post URN from URL: {draft.target_post_url}\n"
            "Ensure the URL is a direct LinkedIn post link (not a profile page)."
        )

    payload = {
        "actor":   person_urn,
        "message": {
            "text": draft.comment_body,
        },
    }

    with httpx.Client() as client:
        resp = client.post(
            f"{LINKEDIN_API_BASE}/socialActions/{post_urn}/comments",
            headers=_linkedin_headers(token["access_token"]),
            json=payload,
        )
        resp.raise_for_status()

    comment_id = resp.headers.get("x-restli-id", "")
    return comment_id


# ── Publish Cycle (called by launchd every 30 min) ───────────────────────────

def run_publish_cycle() -> str:
    """
    Check for scheduled drafts whose time has arrived and publish them.
    Called by: python3 orchestrate.py linkedin publish (via launchd)
    """
    try:
        token = _get_valid_token()
    except RuntimeError as e:
        return f"Skipped: {e}"

    drafts = load_drafts()
    now    = datetime.now()
    published = []
    errors    = []

    for draft in drafts:
        if draft.status != "scheduled":
            continue
        if not draft.scheduled_time:
            continue
        try:
            sched_dt = datetime.fromisoformat(draft.scheduled_time)
        except ValueError:
            continue
        if sched_dt > now:
            continue  # Not yet time

        try:
            if draft.type == "post":
                post_id = publish_post(draft, token)
                draft.linkedin_post_id = post_id
            else:
                comment_id = publish_comment(draft, token)
                draft.linkedin_post_id = comment_id

            draft.status       = "published"
            draft.published_at = datetime.now().isoformat()
            published.append(f"{draft.type}: {draft.target_post_author or draft.positioning_angle or draft.draft_id[:8]}")

        except Exception as e:
            errors.append(f"{draft.draft_id[:8]}: {e}")

    if published or errors:
        save_drafts(drafts)

    parts = []
    if published:
        parts.append(f"Published {len(published)}: {', '.join(published)}")
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}")
    return "; ".join(parts) if parts else "Nothing scheduled for now"


# ── Auth Status ───────────────────────────────────────────────────────────────

def get_auth_status() -> dict:
    """Return auth status for the web dashboard."""
    token = load_token()
    if not token:
        return {"connected": False, "expires_at": None, "person_name": None}
    expiry_str = token.get("expires_at", "")
    connected  = True
    if expiry_str:
        try:
            connected = datetime.fromisoformat(expiry_str) > datetime.now()
        except ValueError:
            connected = False
    return {
        "connected":   connected,
        "expires_at":  expiry_str[:10] if expiry_str else None,
        "person_name": token.get("person_name", ""),
        "person_urn":  token.get("person_urn", ""),
    }


# ── Status Display ────────────────────────────────────────────────────────────

def show_status() -> str:
    drafts = load_drafts()
    pending   = [d for d in drafts if d.status == "pending"]
    scheduled = [d for d in drafts if d.status == "scheduled"]
    published = [d for d in drafts if d.status == "published"]
    discarded = [d for d in drafts if d.status == "discarded"]

    table = Table(title="LinkedIn Engine Status", box=box.ROUNDED)
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Next", style="dim")

    next_sched = ""
    if scheduled:
        times = sorted(d.scheduled_time for d in scheduled if d.scheduled_time)
        if times:
            try:
                dt = datetime.fromisoformat(times[0])
                next_sched = dt.strftime("%a %b %-d · %-I:%M %p ET")
            except ValueError:
                next_sched = times[0]

    table.add_row("[yellow]Pending review[/yellow]", str(len(pending)),  "—")
    table.add_row("[blue]Scheduled[/blue]",          str(len(scheduled)), next_sched)
    table.add_row("[green]Published[/green]",         str(len(published)), "—")
    table.add_row("[dim]Discarded[/dim]",             str(len(discarded)), "—")
    console.print(table)

    auth = get_auth_status()
    if auth["connected"]:
        console.print(f"\n[green]LinkedIn: Connected[/green] as {auth['person_name']} · expires {auth['expires_at']}")
    else:
        console.print("\n[red]LinkedIn: Not connected — run: python3 orchestrate.py linkedin auth[/red]")

    return f"pending={len(pending)} scheduled={len(scheduled)} published={len(published)}"


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def run(args=None) -> str:
    subcommand = getattr(args, "linkedin_cmd", None)
    no_enrich  = getattr(args, "no_enrich", False)

    if subcommand == "auth":
        token = authenticate_linkedin()
        return f"Authenticated as {token.get('person_name','')}"

    elif subcommand == "status":
        return show_status()

    elif subcommand == "publish":
        result = run_publish_cycle()
        console.print(f"[green]{result}[/green]")
        return result

    elif subcommand == "scan":
        # Scrape feed + generate comment drafts
        apify_key = os.environ.get("APIFY_API_KEY", "")
        new_drafts = []

        if apify_key:
            console.print("[bold]Scraping LinkedIn feed via Apify...[/bold]")
            posts = scrape_linkedin_feed(apify_key, max_posts=30)
            console.print(f"  Found {len(posts)} posts, {len(_filter_relevant_posts(posts))} relevant")

            if not no_enrich and posts:
                console.print("[bold]Generating comment drafts...[/bold]")
                comment_drafts = draft_comments_batch(posts, n=10)
                new_drafts.extend(comment_drafts)
                console.print(f"  Generated {len(comment_drafts)} comment drafts")
        else:
            console.print("[yellow]APIFY_API_KEY not set — skipping feed scrape[/yellow]")

        # Also import content drafts from Module 1
        console.print("[bold]Importing post drafts from content cache...[/bold]")
        post_drafts = import_content_drafts()
        new_drafts.extend(post_drafts)
        console.print(f"  Imported {len(post_drafts)} post drafts")

        if new_drafts:
            existing = load_drafts()
            existing.extend(new_drafts)
            save_drafts(existing)
            console.print(Panel(
                f"[bold green]{len(new_drafts)} drafts added.[/bold green]\n"
                f"Review + approve at: [cyan]http://localhost:5050[/cyan] → LinkedIn tab\n"
                f"Or run: [cyan]python3 orchestrate.py linkedin status[/cyan]",
                border_style="green"
            ))
        else:
            console.print("[dim]No new drafts generated.[/dim]")

        return f"Added {len(new_drafts)} drafts"

    elif subcommand == "draft":
        # Import content drafts only (no scraping)
        post_drafts = import_content_drafts()
        if post_drafts:
            existing = load_drafts()
            existing.extend(post_drafts)
            save_drafts(existing)
            console.print(f"[green]Imported {len(post_drafts)} post drafts from content cache[/green]")
        else:
            console.print("[dim]No new drafts to import (run 'content' first)[/dim]")
        return f"Imported {len(post_drafts)} drafts"

    elif subcommand == "comment":
        # Manual comment from URL
        url  = getattr(args, "url", None)
        auth = getattr(args, "author", "")
        auth_title = getattr(args, "author_title", "")
        if not url:
            console.print("[red]--url required for 'linkedin comment'[/red]")
            return "error: --url required"
        if no_enrich:
            console.print("[yellow]--no-enrich: skipping Claude draft[/yellow]")
            return "skipped (no-enrich)"
        draft = add_manual_comment_from_url(url, author=auth, author_title=auth_title)
        if draft:
            console.print(Panel(
                f"[bold green]Comment draft created[/bold green]\n\n"
                f"Author : {draft.target_post_author}\n"
                f"Quality: {draft.quality_score}/10\n\n"
                f"[dim]{draft.comment_body[:200]}...[/dim]\n\n"
                f"Review at: [cyan]http://localhost:5050[/cyan] → LinkedIn tab",
                border_style="green"
            ))
            return f"Draft created for {draft.target_post_author}"
        return "Draft generation failed (quality below threshold)"

    elif subcommand == "post":
        # Manual original post
        body = getattr(args, "body", "")
        source_url = getattr(args, "url", "")
        if not body:
            console.print("[red]--body required for 'linkedin post'[/red]")
            return "error: --body required"
        draft = add_manual_post(body, source_url=source_url)
        console.print(f"[green]Post draft created (ID: {draft.draft_id[:8]})[/green]")
        console.print(f"Review at: http://localhost:5050 → LinkedIn tab")
        return f"Post draft created"

    else:
        show_status()
        return ""
