"""
Company Intelligence — fetch Google News headlines for a target company.
No AI calls on Render. Synthesis is done via Claude Pro through the MCP layer.
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


async def generate_company_brief(company, session) -> str:
    """
    Assemble a structured intel snapshot: Google News headlines + contacts +
    outreach history + open roles. No AI call — readable as-is, and serves as
    rich context for the MCP layer (get_interview_prep / update_company_intel)
    to synthesize via Claude Pro.
    """
    from sqlmodel import select
    from app.models import Contact, OutreachRecord, Lead

    company_id = company.id
    company_name = company.name
    fetched_at = datetime.utcnow().strftime("%Y-%m-%d")

    # Google News headlines
    news = await fetch_news(company_name)
    news_block = "\n".join(news) if news else "No recent news found."

    # Contacts
    contacts = session.exec(select(Contact).where(Contact.company_id == company_id)).all()
    contacts_block = "\n".join(
        f"- {c.name} ({c.title or 'unknown title'})"
        for c in contacts
    ) if contacts else "None on record."

    # Outreach history
    outreach = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.company_id == company_id)
        .order_by(OutreachRecord.sent_at.desc())
    ).all()
    outreach_block = "\n".join(
        f"- [{(o.sent_at or '')[:10]}] {o.channel} ({o.response_status}): {o.subject or ''}"
        for o in outreach
    ) if outreach else "None on record."

    # Open roles
    leads = session.exec(
        select(Lead).where(Lead.company_id == company_id, Lead.status == "active")
    ).all()
    roles_block = "\n".join(
        l.title + (f" — {l.location}" if l.location else "")
        for l in leads
    ) if leads else "None tracked."

    return (
        f"Intel snapshot as of {fetched_at}\n\n"
        f"RECENT NEWS:\n{news_block}\n\n"
        f"CONTACTS:\n{contacts_block}\n\n"
        f"OUTREACH:\n{outreach_block}\n\n"
        f"OPEN ROLES:\n{roles_block}"
    )
