"""
Content Generator — FinTech news → LinkedIn post drafts via Claude Opus.
Simplified version of skills/content_intelligence.py for the v2 API.
"""

import re
import json
import feedparser
import anthropic

EXECUTIVE_PROFILE = None

RSS_FEEDS = [
    "https://techcrunch.com/category/fintech/feed/",
    "https://www.pymnts.com/feed/",
    "https://www.finextra.com/rss/headlines.aspx",
    "https://paymentsdive.com/feeds/news/",
    "https://bankingdive.com/feeds/news/",
]


def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


async def generate_linkedin_drafts(days: int = 7, count: int = 3) -> list:
    """Pull FinTech news and generate LinkedIn post drafts."""
    from datetime import datetime, timedelta
    from app.database import engine
    from app.models import ContentDraft
    from sqlmodel import Session

    cutoff = datetime.utcnow() - timedelta(days=days)
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
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
                    "source": feed.feed.get("title", feed_url),
                })
        except Exception:
            continue

    if not articles:
        return []

    # Select top articles for drafting
    selected = articles[:count * 2]
    client = anthropic.Anthropic()
    profile = _get_profile()
    saved = []

    for article in selected[:count]:
        prompt = f"""Write a contrarian LinkedIn post (200-280 words) for Santiago Aldana based on this article.

ARTICLE: {article['title']}
SUMMARY: {article['summary']}
SOURCE: {article['source']}

AUTHOR PROFILE:
{profile}

POST REQUIREMENTS:
- Open with a contrarian observation that challenges the article or highlights a gap
- Reference one specific Santiago credential (SoyYo, Avianca, Uff Móvil, MIT Sloan)
- End with a sharp, genuinely debatable question
- No generic phrases: no "excited", "great article", no excessive hashtags
- No emojis unless making a specific rhetorical point
- First person, direct voice

Also score:
- controversy_score (1-10): how much this challenges conventional wisdom
- risk_score (1-10): credibility risk from the contrarian angle

Return JSON (no markdown):
{{
  "body": "<full post text>",
  "controversy_score": <int>,
  "risk_score": <int>
}}"""

        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            data = json.loads(raw)

            controversy = float(data.get("controversy_score", 5))
            risk = float(data.get("risk_score", 5))
            net_score = round(controversy - (risk * 0.4), 2)

            with Session(engine) as session:
                draft = ContentDraft(
                    source_url=article["url"],
                    source_title=article["title"],
                    body=data["body"],
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


async def regenerate_linkedin_draft(
    original_body: str,
    source_title: str,
    instructions: str,
) -> tuple:
    """
    Regenerate a LinkedIn draft based on natural language edit instructions.
    Returns (new_body, new_net_score).
    """
    client = anthropic.Anthropic()

    prompt = f"""You are editing a LinkedIn post for Santiago Aldana, an executive in FinTech/AI/payments.

ORIGINAL POST:
{original_body}

SOURCE ARTICLE: {source_title}

EDIT INSTRUCTIONS FROM SANTIAGO:
{instructions}

Rewrite the post following the edit instructions exactly. Keep the same general topic and voice but apply the requested changes.

Rules:
- 150–250 words
- Strong opening hook (no "I", question, or bold statement)
- First-person executive voice
- Ends with a clear takeaway or question
- No hashtags, no emojis

Return JSON only (no markdown):
{{
  "body": "<rewritten post>",
  "controversy_score": <1-10, how thought-provoking>,
  "risk_score": <1-10, reputational risk>
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    data = json.loads(raw)

    controversy = float(data.get("controversy_score", 5))
    risk = float(data.get("risk_score", 5))
    net_score = round(controversy - (risk * 0.4), 2)

    return data["body"], net_score
