"""Extract salary range from job description text."""

import re
import json
import os


def _regex_extract(text: str) -> dict:
    """Try to extract salary via regex. Returns partial dict (may have None values)."""
    result = {"min": None, "max": None, "currency": "USD", "notes": None}

    # Detect non-USD currencies
    if re.search(r'\bCAD\b|\bC\$', text):
        result["currency"] = "CAD"
    elif re.search(r'\bGBP\b|£', text):
        result["currency"] = "GBP"
    elif re.search(r'\bEUR\b|€', text):
        result["currency"] = "EUR"

    # Normalize text for easier matching
    t = text.replace(",", "")

    # Range patterns: $120K - $150K  or  $120,000 - $150,000
    m = re.search(r'\$\s*(\d{2,3})[Kk]\s*[-–to]+\s*\$\s*(\d{2,3})[Kk]', t)
    if m:
        result["min"] = int(m.group(1)) * 1000
        result["max"] = int(m.group(2)) * 1000
    else:
        m = re.search(r'\$\s*(\d{2,3})(\d{3})\s*[-–to]+\s*\$\s*(\d{2,3})(\d{3})', t)
        if m:
            result["min"] = int(m.group(1) + m.group(2))
            result["max"] = int(m.group(3) + m.group(4))
        else:
            # Single figure: $120K or $120,000
            m = re.search(r'\$\s*(\d{2,3})[Kk]', t)
            if m:
                result["min"] = int(m.group(1)) * 1000
            else:
                m = re.search(r'\$\s*(\d{2,3})(\d{3})', t)
                if m:
                    result["min"] = int(m.group(1) + m.group(2))

    # Notes — compensation qualifiers
    notes = []
    if re.search(r'\bequity\b|\bstock\b|\bRSU\b|\bESOP\b', text, re.I):
        notes.append("equity")
    if re.search(r'\bbonus\b', text, re.I):
        notes.append("bonus")
    if re.search(r'\bcommission\b', text, re.I):
        notes.append("commission")
    if re.search(r'\bcompetitive\b', text, re.I):
        notes.append("competitive compensation")
    if notes:
        result["notes"] = ", ".join(notes)

    return result


async def extract_salary(description: str, title: str = "") -> dict:
    """Return {min, max, currency, notes}. All nullable."""
    if not description:
        return {"min": None, "max": None, "currency": "USD", "notes": None}

    result = _regex_extract(description)

    # If regex found salary, return immediately
    if result["min"] is not None:
        return result

    # Haiku fallback — only if no salary found via regex
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return result

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""Extract the salary range from this job description. Return JSON only (no markdown):
{{"min": integer or null, "max": integer or null, "currency": "USD", "notes": "string or null"}}

Rules:
- min/max are annual integers in full dollars (e.g. 120000 not 120K)
- currency: USD unless clearly stated otherwise
- notes: mention equity, bonus, "competitive", etc. if present; null if not
- If no salary info at all, return all nulls

Job title: {title}
Description (first 3000 chars):
{description[:3000]}"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        parsed = json.loads(raw)
        return {
            "min": parsed.get("min"),
            "max": parsed.get("max"),
            "currency": parsed.get("currency", "USD") or "USD",
            "notes": parsed.get("notes"),
        }
    except Exception:
        return result
