"""Waterfall contact finder.

Tries sources in order, merges results:
  1. Crunchbase API  → founder/exec names from funding round data
  2. Apollo API      → verified email + LinkedIn for those names
  3. Google → LinkedIn profile scrape
  4. GitHub org public members
  5. Claude Haiku synthesis (generates likely exec names + emails)

Crunchbase and Apollo steps are skipped silently if API keys are absent.
"""

import os
import re
import json
import httpx
from bs4 import BeautifulSoup

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
CRUNCHBASE_API_KEY = os.environ.get("CRUNCHBASE_API_KEY", "")

# Headers to avoid trivial bot blocks
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def find_contacts(company_name: str, company_id: int, domain: str = None) -> list[dict]:
    """Run waterfall, return list of contact dicts with keys: name, title, email, linkedin_url, source."""
    # Step 1: Crunchbase → founder/exec names
    crunchbase_contacts = await _try_crunchbase(company_name)

    # Step 2: Apollo → enrich each Crunchbase contact with verified email
    if crunchbase_contacts and APOLLO_API_KEY:
        enriched = []
        for c in crunchbase_contacts:
            apollo = await _try_apollo(c["name"], domain or _slugify(company_name) + ".com")
            if apollo:
                c.update({k: v for k, v in apollo.items() if v and not c.get(k)})
                c["source"] = "crunchbase+apollo"
            enriched.append(c)
        return enriched

    if crunchbase_contacts:
        return crunchbase_contacts

    # Step 3: Google → LinkedIn
    results = await _try_google_linkedin(company_name)
    if results:
        # Try Apollo enrichment on Google results too
        if APOLLO_API_KEY and domain:
            for c in results:
                apollo = await _try_apollo(c["name"], domain)
                if apollo:
                    c.update({k: v for k, v in apollo.items() if v and not c.get(k)})
                    c["source"] = "linkedin+apollo"
        return results

    # Step 4: GitHub
    results = await _try_github(company_name)
    if results:
        return results

    # Step 5: Claude synthesis
    results = await _try_claude_synthesis(company_name, domain)
    return results


async def _try_crunchbase(company_name: str) -> list[dict]:
    """Fetch founder/exec names from Crunchbase. Returns [] if key absent or not found."""
    if not CRUNCHBASE_API_KEY:
        return []

    slug = _slugify(company_name)
    url = (
        f"https://api.crunchbase.com/api/v4/entities/organizations/{slug}"
        f"?user_key={CRUNCHBASE_API_KEY}"
        f"&field_ids=founder_identifiers,leadership_highlights,short_description"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return []

        data = resp.json().get("properties", {})
        contacts = []

        # Founders
        for f in (data.get("founder_identifiers") or []):
            name = f.get("value", "")
            if name:
                contacts.append({"name": name, "title": "Co-Founder", "email": None, "linkedin_url": None, "source": "crunchbase"})

        # Leadership highlights (structured exec list)
        for item in (data.get("leadership_highlights") or []):
            name = item.get("person_identifier", {}).get("value", "")
            title = item.get("title", "")
            if name and not any(c["name"] == name for c in contacts):
                contacts.append({"name": name, "title": title, "email": None, "linkedin_url": None, "source": "crunchbase"})

        return contacts[:5]
    except Exception:
        return []


async def _try_apollo(name: str, domain: str) -> dict | None:
    """Look up a person by name + company domain on Apollo. Returns enriched fields or None."""
    if not APOLLO_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.apollo.io/v1/people/search",
                json={
                    "api_key": APOLLO_API_KEY,
                    "q_organization_domains": domain,
                    "q_keywords": name,
                    "page": 1,
                    "per_page": 1,
                },
            )
        if resp.status_code != 200:
            return None

        people = resp.json().get("people", [])
        if not people:
            return None

        p = people[0]
        return {
            "email": p.get("email"),
            "linkedin_url": p.get("linkedin_url"),
            "title": p.get("title"),
        }
    except Exception:
        return None


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
    from skills.shared import MODEL_HAIKU

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
