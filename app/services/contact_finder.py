"""Zero-cost waterfall contact finder.

Tries sources in order, stops at first success:
  1. Google → LinkedIn profile scrape
  2. GitHub org public members
  3. Claude Haiku synthesis (generates likely exec names + emails)
"""

import re
import json
import httpx
from bs4 import BeautifulSoup

from skills.shared import MODEL_HAIKU

# Headers to avoid trivial bot blocks
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def find_contacts(company_name: str, company_id: int, domain: str = None) -> list[dict]:
    """Run waterfall, return list of contact dicts with keys: name, title, email, linkedin_url, source."""
    results = await _try_google_linkedin(company_name)
    if results:
        return results

    results = await _try_github(company_name)
    if results:
        return results

    results = await _try_claude_synthesis(company_name, domain)
    return results


async def _try_google_linkedin(company_name: str) -> list[dict]:
    query = f'site:linkedin.com/in "{company_name}" ("VP" OR "CPO" OR "Head of" OR "Director" OR "Chief")'
    url = f"https://www.google.com/search?q={httpx.URL('', params={'q': query}).params}&num=10&hl=en"

    try:
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=10) as client:
            resp = await client.get(
                "https://www.google.com/search",
                params={"q": query, "num": 10, "hl": "en"},
            )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        contacts = []

        for result in soup.select("div.g, div[data-sokoban-container]"):
            h3 = result.find("h3")
            if not h3:
                continue
            title_text = h3.get_text(strip=True)

            # LinkedIn result titles typically: "Name - Title at Company | LinkedIn"
            link_tag = result.find("a", href=True)
            href = link_tag["href"] if link_tag else ""
            if "linkedin.com/in/" not in href:
                continue

            # Parse "Name - Title at Company"
            parts = re.split(r" [-–] | at | \| ", title_text)
            if len(parts) < 2:
                continue

            name = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else ""

            # Skip if title contains company name (likely a company page, not person)
            if not name or len(name.split()) > 5:
                continue

            # Clean up LinkedIn URL
            linkedin_url = href.split("?")[0] if "linkedin.com" in href else ""

            contacts.append({
                "name": name,
                "title": title,
                "email": None,
                "linkedin_url": linkedin_url,
                "source": "linkedin",
            })

            if len(contacts) >= 3:
                break

        return contacts

    except Exception:
        return []


def _slugify(name: str) -> str:
    """Convert company name to likely GitHub org slug."""
    slug = name.lower()
    slug = re.sub(r"['’]", "", slug)           # remove apostrophes
    slug = re.sub(r"[^a-z0-9]+", "-", slug)         # non-alphanumeric → dash
    slug = slug.strip("-")
    # Remove common suffixes
    for suffix in ["-inc", "-corp", "-llc", "-ltd", "-technologies", "-technology",
                   "-solutions", "-software", "-labs", "-ai", "-co"]:
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return slug


async def _try_github(company_name: str) -> list[dict]:
    slug = _slugify(company_name)
    url = f"https://api.github.com/orgs/{slug}/public_members"

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})

        if resp.status_code != 200:
            return []

        members = resp.json()
        if not members or not isinstance(members, list):
            return []

        contacts = []
        # Fetch name for first few members (rate-limit: 60/hr unauthenticated)
        for m in members[:5]:
            login = m.get("login", "")
            name = m.get("name") or login
            contacts.append({
                "name": name,
                "title": "Engineer",  # GitHub doesn't expose titles
                "email": None,
                "linkedin_url": None,
                "source": "github",
            })

        return contacts[:3]

    except Exception:
        return []


async def _try_claude_synthesis(company_name: str, domain: str = None) -> list[dict]:
    import anthropic
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    if not domain:
        slug = _slugify(company_name)
        domain = f"{slug}.com"

    prompt = f"""You are a B2B sales researcher. Given a company, generate 2-3 realistic senior executive contacts who likely work there.

Company: {company_name}
Domain: {domain}

For each contact, use common executive naming patterns. For email, use the most likely format for that company (first@domain.com, first.last@domain.com, etc.).

Return JSON only (no markdown):
{{
  "contacts": [
    {{"name": "First Last", "title": "Chief Product Officer", "email": "first@{domain}", "notes": "Likely CPO based on company size/stage"}},
    {{"name": "First Last", "title": "VP of Engineering", "email": "first.last@{domain}", "notes": "..."}}
  ]
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

        data = json.loads(raw)
        return [
            {
                "name": c.get("name", ""),
                "title": c.get("title", ""),
                "email": c.get("email"),
                "linkedin_url": None,
                "source": "claude",
            }
            for c in data.get("contacts", [])
            if c.get("name")
        ]

    except Exception:
        return []
