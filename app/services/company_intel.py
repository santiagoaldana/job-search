"""
Company Intelligence — generate a 300-word brief on a target company
using Google News RSS + Claude Opus.
"""

import re
import anthropic
import httpx
from xml.etree import ElementTree

EXECUTIVE_PROFILE = None


def _get_profile() -> str:
    global EXECUTIVE_PROFILE
    if EXECUTIVE_PROFILE is None:
        from skills.shared import EXECUTIVE_PROFILE as EP
        EXECUTIVE_PROFILE = EP
    return EXECUTIVE_PROFILE


async def fetch_news(company_name: str, max_items: int = 5) -> list:
    """Fetch recent news via Google News RSS (free, no API key)."""
    query = company_name.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    items = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        root = ElementTree.fromstring(resp.text)
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            pub = item.findtext("pubDate") or ""
            items.append(f"- {title} ({pub[:16]})")
            if len(items) >= max_items:
                break
    except Exception:
        pass
    return items


async def generate_company_brief(company_name: str) -> str:
    """
    Generate a 300-word company intelligence brief.
    Includes: funding stage, leadership, recent moves, why Santiago fits NOW.
    """
    news = await fetch_news(company_name)
    news_text = "\n".join(news) if news else "No recent news found."

    client = anthropic.Anthropic()
    profile = _get_profile()

    prompt = f"""You are a strategic analyst helping an executive prepare for a job opportunity.

COMPANY: {company_name}
RECENT NEWS:
{news_text}

CANDIDATE PROFILE:
{profile}

Write a 300-word company intelligence brief covering:
1. Company stage & funding (Series B/C/public, approximate valuation if known)
2. Core product/service and differentiation
3. Leadership team highlights (CEO background, key hires)
4. Recent strategic moves (funding, acquisitions, partnerships, product launches)
5. Why Santiago is specifically relevant NOW (1-2 sentences linking his experience to their current moment)

Be direct and factual. If you don't know something, say "unknown" rather than guessing.
Write in third person about the company, first person about Santiago's fit."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
