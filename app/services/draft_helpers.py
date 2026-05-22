"""Shared helpers for building outreach draft openers and questions."""

import re


def _derive_expertise_from_title(title: str, company_name: str) -> str:
    t = title.lower()
    if any(k in t for k in ("tokeniz", "vault", "card")):
        return "embedded card products and tokenization infrastructure"
    if any(k in t for k in ("payment", "acquiring", "issuing")):
        return "payments infrastructure and orchestration"
    if any(k in t for k in ("identity", "kyc", "aml", "fraud")):
        return "digital identity and compliance"
    if any(k in t for k in ("lending", "credit", "loan")):
        return "embedded lending and credit products"
    if any(k in t for k in ("compliance", "risk", "regulatory")):
        return "risk and compliance frameworks"
    if any(k in t for k in ("engineer", "platform", "infrastructure", "architect")):
        return "platform architecture and developer experience"
    if any(k in t for k in ("product", "growth", "strategy")):
        return f"product strategy at {company_name}"
    return f"what you are building at {company_name}"


_AMBIGUOUS_NAMES = {
    "stripe", "square", "plaid", "marqeta", "synctera", "sardine",
    "brex", "ramp", "unit", "column", "mercury", "relay", "grasshopper",
}

_HEADLINE_SKIP = ("hiring", "job", "career", "apply", "underwear", "stare", "dies", "kickstarter", "grade 1")


def _pick_headline(news_headlines: list, company_name: str = "") -> str:
    """Return the best headline: prefer company-as-subject, skip noise."""
    candidates = []
    for raw in news_headlines:
        cleaned = re.sub(r"\s*\([^)]{0,25}\)\s*$", "", raw.strip().lstrip("- ")).strip()
        cleaned = re.sub(r"\s+-\s+[^-]+$", "", cleaned).strip()
        if not cleaned or len(cleaned) < 20:
            continue
        if any(k in cleaned.lower() for k in _HEADLINE_SKIP):
            continue
        candidates.append(cleaned)
    if company_name:
        for c in candidates:
            if c.lower().startswith(company_name.lower()):
                return c
    return candidates[0] if candidates else ""


def _humanize_headline(headline: str, company_name: str) -> str:
    """Turn a news headline into a natural first-person observation."""
    if headline.lower().startswith(company_name.lower()):
        return f"I saw {headline}."
    return f"I saw that {headline}."


def _extract_curated_opener(intel: str) -> str:
    """Pull the first substantive sentence from a Claude-written intel_summary (not an RSS dump)."""
    _SKIP_PREFIXES = ("intel snapshot", "recent news", "contacts:", "outreach:", "open roles:", "---")
    for line in intel.splitlines():
        line = line.strip()
        if not line or any(line.lower().startswith(p) for p in _SKIP_PREFIXES) or line.startswith("-"):
            continue
        sentence = re.split(r"(?<=[.!?])\s", line)[0].strip()
        if len(sentence) > 30:
            return sentence
    return ""
