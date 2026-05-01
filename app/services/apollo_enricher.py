"""Apollo organization enrichment — populates funding_stage, headcount_range, org_notes."""

import os
import httpx


async def enrich_company(name: str) -> dict:
    """Return {funding_stage, headcount_range, description} for a company name via Apollo."""
    api_key = os.environ.get("APOLLO_API_KEY", "")
    if not api_key:
        return {}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.apollo.io/v1/organizations/search",
            json={"q_organization_name": name, "page": 1, "per_page": 1},
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
        )
    if not r.is_success:
        return {}
    orgs = r.json().get("organizations", [])
    if not orgs:
        return {}
    org = orgs[0]

    # funding_stage: Apollo free tier doesn't return latest_funding_stage,
    # so infer from revenue + headcount heuristics
    raw_stage = (org.get("latest_funding_stage") or "").lower().replace(" ", "_")
    stage_map = {
        "series_b": "series_b", "series_c": "series_c", "series_d": "series_d",
        "public": "public", "ipo": "public", "private_equity": "series_d",
        "seed": "unknown", "angel": "unknown", "series_a": "unknown",
    }
    funding = stage_map.get(raw_stage) if raw_stage else None
    if not funding:
        funding = _infer_stage(
            org.get("publicly_traded_symbol"),
            org.get("organization_revenue"),
            org.get("estimated_num_employees"),
        )

    headcount = _map_headcount(org.get("estimated_num_employees"))

    # Build description from available free-tier fields
    description = (org.get("short_description") or "").strip()
    if not description:
        description = _build_description(org)

    return {"funding_stage": funding, "headcount_range": headcount, "description": description}


def _infer_stage(ticker, revenue, headcount) -> str:
    if ticker:
        return "public"
    rev = revenue or 0
    hc = headcount or 0
    if rev >= 500_000_000 or hc >= 1000:
        return "series_d"
    if rev >= 50_000_000 or hc >= 300:
        return "series_c"
    if rev >= 10_000_000 or hc >= 100:
        return "series_b"
    return "unknown"


def _build_description(org: dict) -> str:
    parts = []
    industry = org.get("industry") or ""
    if industry:
        parts.append(industry.title())
    city = org.get("city") or ""
    country = org.get("country") or ""
    location = ", ".join(filter(None, [city, country]))
    if location:
        parts.append(f"based in {location}")
    rev = org.get("organization_revenue_printed") or ""
    if rev:
        parts.append(f"~{rev} revenue")
    hc = org.get("estimated_num_employees")
    if hc:
        parts.append(f"{hc} employees")
    founded = org.get("founded_year")
    if founded:
        parts.append(f"founded {founded}")
    # Top keywords (first 6, skip generic ones)
    skip = {"services", "b2b", "b2c", "d2c", "finance", "banking", "consumers", "internet", "roi"}
    keywords = [k for k in (org.get("keywords") or []) if k.lower() not in skip][:6]
    if keywords:
        parts.append("· " + ", ".join(keywords))
    return ". ".join(parts[:5]) + ("  " + parts[5] if len(parts) > 5 else "")


def _map_headcount(n) -> str:
    if not n:
        return "unknown"
    if n <= 50:
        return "1-50"
    if n <= 200:
        return "51-200"
    if n <= 500:
        return "201-500"
    return "500+"
