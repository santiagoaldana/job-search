"""
Content Generator — LinkedIn post drafts via Claude Opus.
Simplified version of skills/content_intelligence.py for the v2 API.
"""

import re
import json
import feedparser
import anthropic

EXECUTIVE_PROFILE = None

# Fallback feeds used only when ContentFeed table is empty
FALLBACK_FEEDS = [
    {"name": "TechCrunch FinTech", "url": "https://techcrunch.com/category/fintech/feed/", "category": "news"},
    {"name": "PYMNTS", "url": "https://www.pymnts.com/feed/", "category": "news"},
    {"name": "Finextra", "url": "https://www.finextra.com/rss/headlines.aspx", "category": "news"},
    {"name": "Payments Dive", "url": "https://paymentsdive.com/feeds/news/", "category": "news"},
    {"name": "Banking Dive", "url": "https://bankingdive.com/feeds/news/", "category": "news"},
]

# ── Prompts (edit these to tune tone and persona) ─────────────────────────────

NEWS_PROMPT = """\
You are a Strategic Executive Architect. You combine the high-stakes positioning of a PR Expert, \
the market-matching insight of an Executive Search Consultant, and the tactical communication style \
of a Leadership Coach. Your goal is to help Santiago Aldana build Intellectual Authority on LinkedIn \
without ever appearing to be job hunting.

AUTHOR PROFILE:
{profile}

ARTICLE: {title}
SUMMARY: {summary}
SOURCE: {source}
SOURCE TYPE: {source_type}

WRITING RULES:
- First Principles: Break the topic into fundamental truths. Not "improving payments" but "the atomic unit of trust in digital exchange."
- Anti-Sales Mandate: No hashtags of any kind. The post must make Santiago appear deeply embedded in the future of industry.
- Style: Clever, minimalist, authoritative. Short punchy sentences. No corporate jargon — use "friction" not "synergistic challenges."
- Hook: Start with a Pattern Interrupt — a first line that challenges a common assumption or states a surprising fact. Never open with "I".
- If SOURCE TYPE is "thought_leader": frame the post as peer-level commentary or a direct response to the author's idea. Cite them by name. Santiago is engaging as an intellectual equal, not summarizing their work.
- If SOURCE TYPE is "publication" or "news": analyze the article through three lenses:
  1. Macro Trend: Why does this matter to the economy/industry right now?
  2. The "So What?": What is the non-obvious insight Santiago has, grounded in his specific experience (SoyYo, Avianca, Uff Móvil, MIT Sloan)?
  3. Call to Conversation: End with a high-level question that invites peers (CEOs, Founders) to comment.
- The Execution Gap: When relevant, highlight that technology is a commodity — "Institutional Wisdom" (navigating human resistance, process redesign) is the real bottleneck. Position Santiago as the strategist who understands both the code and the culture, equally capable as a hands-on entrepreneur and a senior executive.
- Length: 180–260 words. No emojis.

Score:
- controversy_score (1-10): how much this challenges conventional wisdom
- risk_score (1-10): reputational risk

Return JSON only (no markdown):
{{"body": "<full post>", "controversy_score": <int>, "risk_score": <int>}}"""

COMPOSE_PROMPT = """\
You are a Strategic Executive Architect. You combine the high-stakes positioning of a PR Expert, \
the market-matching insight of an Executive Search Consultant, and the tactical communication style \
of a Leadership Coach. Your goal is to help Santiago Aldana build Intellectual Authority on LinkedIn \
without ever appearing to be job hunting.

AUTHOR PROFILE:
{profile}

TOPIC / CONTEXT FROM SANTIAGO:
{context}

WRITING RULES:
- First Principles: Break every topic into fundamental truths. Not "improving payments" but "the atomic unit of trust in digital exchange."
- Anti-Sales Mandate: No hashtags (#Hiring, #OpenToWork, or any). The post must make Santiago appear deeply embedded in the future of industry.
- Style: Clever, minimalist, authoritative. Short punchy sentences. No corporate jargon — use "friction" not "synergistic challenges."
- Hook: Start with a Pattern Interrupt — a first line that challenges a common assumption or states a surprising fact. Never open with "I".
- Analyze the topic through three lenses:
  1. Macro Trend: Why does this matter to the economy/industry right now?
  2. The "So What?": What is the non-obvious insight Santiago has, grounded in his specific experience?
  3. Call to Conversation: End with a high-level question that invites peers (CEOs, Founders) to comment.
- The Execution Gap: When relevant, highlight that technology is a commodity — "Institutional Wisdom" (navigating human resistance, process redesign) is the real bottleneck. Position Santiago as the strategist who understands both the code and the culture, equally capable as a hands-on entrepreneur and a senior executive.
- Length: 180–260 words. No emojis.

Score:
- controversy_score (1-10): how much this challenges conventional wisdom
- risk_score (1-10): reputational risk

Return JSON only (no markdown):
{{"body": "<full post>", "controversy_score": <int>, "risk_score": <int>}}"""

REGENERATE_PROMPT = """\
You are a Strategic Executive Architect editing a LinkedIn post for Santiago Aldana, \
a senior FinTech/AI/payments executive.

ORIGINAL POST:
{original_body}

SOURCE ARTICLE: {source_title}

EDIT INSTRUCTIONS FROM SANTIAGO:
{instructions}

Rewrite the post following the edit instructions exactly. Keep the same general topic and voice but apply the requested changes.

Rules:
- 180–260 words. No emojis. No hashtags.
- Strong opening hook — a Pattern Interrupt (never open with "I").
- First-person executive voice, clever and minimalist.
- Ends with a high-level question that invites peer conversation.

Return JSON only (no markdown):
{{"body": "<rewritten post>", "controversy_score": <1-10>, "risk_score": <1-10>}}"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


def _parse_response(raw: str) -> tuple:
    raw = re.sub(r'^```(?:json)?\n?', '', raw.strip())
    raw = re.sub(r'\n?```$', '', raw)
    data = json.loads(raw)
    controversy = float(data.get("controversy_score", 5))
    risk = float(data.get("risk_score", 5))
    net_score = round(controversy - (risk * 0.4), 2)
    return data["body"], net_score, controversy, risk


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_linkedin_drafts(days: int = 7, count: int = 3) -> list:
    """Pull articles from configured feeds and generate LinkedIn post drafts."""
    from datetime import datetime, timedelta
    from app.database import engine
    from app.models import ContentDraft, ContentFeed
    from sqlmodel import Session, select

    # Load active feeds from DB; fall back to hardcoded list if table empty
    with Session(engine) as session:
        db_feeds = session.exec(select(ContentFeed).where(ContentFeed.active == True)).all()

    feeds = [{"name": f.name, "url": f.url, "category": f.category} for f in db_feeds] if db_feeds else FALLBACK_FEEDS

    # Thought leaders get a wider 14-day window; news sources use the requested window
    news_cutoff = datetime.utcnow() - timedelta(days=days)
    leader_cutoff = datetime.utcnow() - timedelta(days=14)

    articles = []
    for feed_def in feeds:
        cutoff = leader_cutoff if feed_def["category"] == "thought_leader" else news_cutoff
        try:
            feed = feedparser.parse(feed_def["url"])
            for entry in feed.entries[:5]:
                pub = entry.get("published_parsed")
                if pub:
                    from time import mktime
                    pub_dt = datetime.fromtimestamp(mktime(pub))
                    if pub_dt < cutoff:
                        continue
                articles.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:500],
                    "source": feed_def["name"],
                    "source_type": feed_def["category"],
                })
        except Exception:
            continue

    if not articles:
        return []

    # Interleave thought leaders and publications for variety
    leaders = [a for a in articles if a["source_type"] == "thought_leader"]
    others = [a for a in articles if a["source_type"] != "thought_leader"]
    interleaved = []
    for pair in zip(leaders, others):
        interleaved.extend(pair)
    interleaved += leaders[len(others):] + others[len(leaders):]
    selected = interleaved[:count]

    client = anthropic.Anthropic()
    profile = _get_profile()
    saved = []

    for article in selected:
        prompt = NEWS_PROMPT.format(
            profile=profile,
            title=article["title"],
            summary=article["summary"],
            source=article["source"],
            source_type=article["source_type"],
        )
        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}],
            )
            body, net_score, controversy, risk = _parse_response(response.content[0].text)

            with Session(engine) as session:
                draft = ContentDraft(
                    source_url=article["url"],
                    source_title=f"{article['source']} — {article['title']}",
                    body=body,
                    net_score=net_score,
                    controversy_score=controversy,
                    risk_score=risk,
                    status="pending",
                )
                session.add(draft)
                session.commit()
                session.refresh(draft)
                saved.append(draft.dict())

        except Exception as e:
            print(f"[content] Error generating draft: {e}")

    return saved


async def compose_linkedin_post(context: str) -> tuple:
    """
    Generate a LinkedIn post from Santiago's own topic/context.
    Returns (body, net_score, controversy_score, risk_score).
    """
    client = anthropic.Anthropic()
    profile = _get_profile()

    prompt = COMPOSE_PROMPT.format(profile=profile, context=context)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )

    body, net_score, controversy, risk = _parse_response(response.content[0].text)
    return body, net_score, controversy, risk


async def regenerate_linkedin_draft(
    original_body: str,
    source_title: str,
    instructions: str,
) -> tuple:
    """Regenerate a LinkedIn draft based on natural language edit instructions."""
    client = anthropic.Anthropic()

    prompt = REGENERATE_PROMPT.format(
        original_body=original_body,
        source_title=source_title,
        instructions=instructions,
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    body, net_score, _, _ = _parse_response(response.content[0].text)
    return body, net_score
