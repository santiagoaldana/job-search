"""Apollo organization enrichment — populates funding_stage, headcount_range, org_notes."""

import os
import asyncio
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
    stage_map = {
        "series_b": "series_b",
        "series_c": "series_c",
        "series_d": "series_d",
        "public": "public",
        "ipo": "public",
        "private_equity": "series_d",
        "seed": "unknown",
        "angel": "unknown",
        "series_a": "unknown",
    }
    raw_stage = (org.get("latest_funding_stage") or "").lower().replace(" ", "_")
    funding = stage_map.get(raw_stage, "unknown")
    headcount = _map_headcount(org.get("estimated_num_employees"))
    description = (org.get("short_description") or "")[:400]
    return {"funding_stage": funding, "headcount_range": headcount, "description": description}


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
