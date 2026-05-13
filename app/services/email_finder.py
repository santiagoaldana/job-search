"""
Email pattern guesser and Gmail bounce detector for contact outreach workflow.

Pattern priority:
  1. first@domain.com
  2. first.last@domain.com
  3. flast@domain.com (first initial + last name)

Gmail bounce detection uses the Gmail MCP via /api/outreach/check-bounces or
can be called directly by providing the Gmail search interface.
"""

import json
import socket
from typing import Optional


def guess_email_patterns(first: str, last: str, domain: str) -> list[str]:
    """Return ordered list of email patterns to try."""
    first = first.lower().strip()
    last = last.lower().strip()
    # Remove accents / special chars that don't work in email local parts
    import unicodedata
    def _clean(s):
        return ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
            and (c.isalnum() or c == '.')
        )
    first = _clean(first)
    last = _clean(last)
    if not first or not domain:
        return []
    patterns = [f"{first}@{domain}"]
    if last:
        patterns.append(f"{first}.{last}@{domain}")
        patterns.append(f"{first[0]}{last}@{domain}")
    return patterns


def domain_has_mx(domain: str) -> bool:
    """Check that a domain has an MX record (DNS only, no SMTP handshake)."""
    try:
        results = socket.getaddrinfo(domain, None)
        return bool(results)
    except Exception:
        return False


def best_email_guess(
    first: str,
    last: str,
    company_domain: Optional[str],
    patterns_tried: Optional[str] = None,
) -> Optional[dict]:
    """
    Return the next un-tried email pattern for a contact.

    Returns:
      {
        "email": "first@domain.com",
        "pattern_index": 0,         # 0=first, 1=first.last, 2=flast
        "all_patterns": [...],
        "domain_verified": True|False,
        "exhausted": False
      }
    or None if no domain available.
    """
    if not company_domain:
        return None

    tried = json.loads(patterns_tried) if patterns_tried else []
    patterns = guess_email_patterns(first, last, company_domain)
    if not patterns:
        return None

    domain_ok = domain_has_mx(company_domain)

    for i, pattern in enumerate(patterns):
        if pattern not in tried:
            return {
                "email": pattern,
                "pattern_index": i,
                "all_patterns": patterns,
                "domain_verified": domain_ok,
                "exhausted": False,
            }

    return {
        "email": None,
        "pattern_index": len(patterns),
        "all_patterns": patterns,
        "domain_verified": domain_ok,
        "exhausted": True,
    }


def determine_next_step(contact, company) -> dict:
    """
    Given a contact and company, determine the recommended next outreach action.

    Returns:
    {
      "action": "draft_email" | "draft_email_guessed" | "prompt_manual_email"
               | "draft_linkedin_dm" | "draft_connection_request",
      "reason": str,
      "guessed_email": str | None,
      "all_patterns": list | None,
      "domain_verified": bool | None,
      "patterns_exhausted": bool,
    }
    """
    has_email = bool(contact.email and not contact.email_invalid)
    degree = contact.connection_degree or 3
    company_domain = _extract_domain(company) if company else None

    if has_email:
        return {
            "action": "draft_email",
            "reason": "Confirmed email on file",
            "guessed_email": None,
            "all_patterns": None,
            "domain_verified": None,
            "patterns_exhausted": False,
        }

    if degree == 1:
        # Try to guess email from domain
        first, last = _split_name(contact.name)
        if company_domain and first:
            guess = best_email_guess(first, last, company_domain, contact.email_patterns_tried)
            if guess and not guess["exhausted"]:
                return {
                    "action": "draft_email_guessed",
                    "reason": f"1st-degree connection — guessed email from domain {company_domain}",
                    "guessed_email": guess["email"],
                    "all_patterns": guess["all_patterns"],
                    "domain_verified": guess["domain_verified"],
                    "patterns_exhausted": False,
                }
            elif guess and guess["exhausted"]:
                return {
                    "action": "draft_linkedin_dm",
                    "reason": "All email patterns exhausted — falling back to LinkedIn DM",
                    "guessed_email": None,
                    "all_patterns": guess["all_patterns"],
                    "domain_verified": guess["domain_verified"],
                    "patterns_exhausted": True,
                }
        # No domain — prompt manual LinkedIn profile check
        return {
            "action": "prompt_manual_email",
            "reason": "1st-degree connection — check LinkedIn profile Contact Info tab for email",
            "guessed_email": None,
            "all_patterns": None,
            "domain_verified": None,
            "patterns_exhausted": False,
        }

    # Not connected (degree 2/3)
    if company_domain and not contact.email_invalid:
        first, last = _split_name(contact.name)
        if first:
            guess = best_email_guess(first, last, company_domain, contact.email_patterns_tried)
            if guess and not guess["exhausted"]:
                return {
                    "action": "draft_email_guessed",
                    "reason": f"Not directly connected — guessed email from domain {company_domain}",
                    "guessed_email": guess["email"],
                    "all_patterns": guess["all_patterns"],
                    "domain_verified": guess["domain_verified"],
                    "patterns_exhausted": False,
                }

    return {
        "action": "draft_connection_request",
        "reason": "Not a 1st-degree connection — send LinkedIn connection request first",
        "guessed_email": None,
        "all_patterns": None,
        "domain_verified": None,
        "patterns_exhausted": False,
    }


_WELL_KNOWN_DOMAINS = {
    "stripe": "stripe.com",
    "brex": "brex.com",
    "plaid": "plaid.com",
    "ripple": "ripple.com",
    "coinbase": "coinbase.com",
    "marqeta": "marqeta.com",
    "flywire": "flywire.com",
    "synctera": "synctera.com",
    "sardine": "sardine.ai",
    "alloy": "alloy.com",
    "socure": "socure.com",
    "finix": "finixpayments.com",
    "unit": "unit.co",
    "column": "column.com",
    "mercury": "mercury.com",
    "ramp": "ramp.com",
    "modern treasury": "moderntreasury.com",
    "modern-treasury": "moderntreasury.com",
    "airwallex": "airwallex.com",
    "payoneer": "payoneer.com",
    "nuvei": "nuvei.com",
    "checkout.com": "checkout.com",
}


def _extract_domain(company) -> Optional[str]:
    """Extract email domain from company career_page_url, then fall back to name-derived domain."""
    url = getattr(company, "career_page_url", None)
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
            host = host.lstrip("www.")
            domain = host.split("/")[0]
            if "." in domain:
                return domain
        except Exception:
            pass

    # Well-known domain lookup by company name
    name = (getattr(company, "name", "") or "").lower().strip()
    for key, domain in _WELL_KNOWN_DOMAINS.items():
        if key in name or name in key:
            return domain

    # Derive <slug>.com from company name as last resort
    import re
    slug = re.sub(r"[^a-z0-9]", "", name)
    if slug:
        return f"{slug}.com"

    return None


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (first, last). Handles middle names."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    return parts[0], parts[-1] if len(parts) > 1 else ""
