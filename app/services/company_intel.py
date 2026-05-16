"""
Company Intelligence — fetch Google News headlines and synthesize intel via Claude Haiku.
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
    Synthesize a strategic intel summary for a company using Claude Haiku.
    Pulls Google News headlines plus DB context (contacts, outreach, open leads).
    Writes a 3-4 paragraph summary focused on Santiago's positioning.
    """
    from sqlmodel import select
    from app.models import Contact, OutreachRecord, Lead

    company_id = company.id
    company_name = company.name

    # Fetch Google News headlines
    news = await fetch_news(company_name)
    news_text = "\n".join(news) if news else "No recent news found."

    # Fetch contacts
    contacts = session.exec(select(Contact).where(Contact.company_id == company_id)).all()
    contacts_text = "\n".join(
        f"- {c.name} ({c.title or 'unknown title'})"
        for c in contacts
    ) if contacts else "No contacts on record."

    # Fetch outreach history
    outreach = session.exec(
        select(OutreachRecord)
        .where(OutreachRecord.company_id == company_id)
        .order_by(OutreachRecord.sent_at.desc())
    ).all()
    outreach_text = "\n".join(
        f"- [{(o.sent_at or '')[:10]}] {o.channel} to {o.contact_name or 'unknown'} ({o.response_status}): {o.subject or ''}"
        for o in outreach
    ) if outreach else "No outreach on record."

    # Fetch open roles
    leads = session.exec(
        select(Lead).where(Lead.company_id == company_id, Lead.status == "active")
    ).all()
    roles_text = "\n".join(
        l.title + (f" ({l.location})" if l.location else "")
        for l in leads
    ) if leads else "No open roles tracked."

    # Existing intel (preserve prior manual notes as context)
    existing_intel = company.intel_summary or ""
    existing_text = f"\nPrior intel on file:\n{existing_intel}\n" if existing_intel else ""

    fetched_at = datetime.utcnow().strftime("%Y-%m-%d")

    prompt = f"""You are a strategic research assistant for Santiago Aldana, an executive with 20+ years in FinTech, payments, embedded banking, and Agentic AI in LATAM. He holds an MIT Sloan MBA. His target roles are C-suite or SVP in payments, BaaS, Agentic AI, digital identity, and embedded finance.

Write a concise strategic intel brief for {company_name} (as of {fetched_at}). Use the context below.

RECENT NEWS:
{news_text}

CONTACTS ON FILE:
{contacts_text}

OUTREACH HISTORY:
{outreach_text}

OPEN ROLES TRACKED:
{roles_text}
{existing_text}
Write 3-4 focused paragraphs covering:
1. What the company does and where it sits in the market
2. Recent moves, funding, or strategic signals from the news
3. Why this company is relevant to Santiago's positioning (payments, BaaS, Agentic AI, digital identity)
4. Any relationship context or next steps worth noting

Be direct. No bullet lists. No filler. Write as if briefing a senior executive before a first call."""

    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        # Fallback: return raw headlines so the field is never empty
        lines = [f"Recent news as of {fetched_at}:"] + news
        lines += [f"\n[Intel synthesis failed: {e}]"]
        return "\n".join(lines)
