"""
Company Intelligence — fetch Google News headlines for a target company.
AI summarization is handled by the MCP layer (Claude Pro), not here.
"""

import httpx
from xml.etree import ElementTree
from datetime import datetime


async def fetch_news(company_name: str, max_items: int = 8) -> list:
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
    Fetch recent news headlines for a company and return them as plain text.
    No AI call — summarization is done via the MCP tool (update_company_intel)
    running in Claude Pro context.
    """
    news = await fetch_news(company_name)
    if not news:
        return f"No recent news found for {company_name}. Use the MCP tool to add intel manually."

    fetched_at = datetime.utcnow().strftime("%Y-%m-%d")
    lines = [f"Recent news as of {fetched_at}:"] + news
    lines += ["", "Use 'update_company_intel' via MCP to add a strategic summary."]
    return "\n".join(lines)
