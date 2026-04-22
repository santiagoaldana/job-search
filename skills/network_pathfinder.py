"""
Network Pathfinder Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Maps shortest path from Santiago's 1st-degree contacts to target hiring
managers or companies. Generates value-proposition-based outreach scripts
via Claude Opus — not templates.

Path logic:
  Path length 1: A direct contact works at target company (1st degree)
  Path length 2: Estimated — contact works at company adjacent or in same sector
                 (true 2nd-degree requires LinkedIn data we don't have)

Script constraints:
  - Para 1: Specific shared context with bridge contact (not "I saw you work at X")
  - Para 2: Why Santiago is reaching out NOW — specific, timely hook
  - Para 3: Low-friction ask (15-min call, specific intro request)
  - Forbidden: "Hope this finds you well", "I'm looking for opportunities", templates
  - Must reference one specific Santiago credential directly relevant to target's world

Usage:
  python3 -m skills.network_pathfinder --target "Stripe" --contacts cv/contacts_export.csv
  python3 -m skills.network_pathfinder --target "John Smith" --company "Checkout.com" --contacts cv/contacts_export.csv --context "Head of Product, payments infrastructure background"
"""

import csv
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
import anthropic

from skills.shared import (
    EXECUTIVE_PROFILE, MODEL_OPUS, MODEL_HAIKU, DATA_DIR, CONTACTS_CSV, compute_net_score
)

# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class Contact:
    first_name: str
    last_name: str
    full_name: str
    company: str
    position: str
    connected_on: str
    email: str = ""


@dataclass
class PathResult:
    target: str                   # company or person name
    path_length: int              # 1 = direct, 2 = estimated
    bridge_contact: Contact       # 1st-degree contact in the path
    company: str                  # target company
    outreach_script: str = ""     # Claude-generated
    rationale: str = ""           # why this angle was chosen


# ── Contact Loader ────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lowercase, strip legal suffixes and whitespace for fuzzy matching."""
    s = s.lower().strip()
    for suffix in [" inc", " llc", " corp", " ltd", " limited", " co.", ", inc.", ", llc", "."]:
        s = s.replace(suffix, "")
    return s.strip()


def load_contacts(csv_path: Path) -> list[Contact]:
    """
    Load LinkedIn contacts CSV export.
    LinkedIn standard export columns (flexible header matching):
      First Name, Last Name, URL, Email Address, Company, Position, Connected On

    Returns list of Contact objects. Empty list if file missing.
    """
    if not csv_path or not csv_path.exists():
        print(f"[Network] Contacts CSV not found at {csv_path}")
        return []

    contacts = []
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Normalize headers to lowercase stripped
            raw_headers = reader.fieldnames or []
            header_map = {h.strip().lower(): h for h in raw_headers}

            def get(row, *keys):
                for k in keys:
                    for hk in header_map:
                        if k in hk:
                            return row.get(header_map[hk], "").strip()
                return ""

            for row in reader:
                first = get(row, "first name", "firstname", "first")
                last = get(row, "last name", "lastname", "last")
                company = get(row, "company", "organization")
                position = get(row, "position", "title", "role")
                connected = get(row, "connected on", "connected")
                email = get(row, "email")
                full = f"{first} {last}".strip()
                if not full or not company:
                    continue
                contacts.append(Contact(
                    first_name=first, last_name=last, full_name=full,
                    company=company, position=position,
                    connected_on=connected, email=email,
                ))
        print(f"[Network] Loaded {len(contacts)} contacts from CSV")
    except Exception as e:
        print(f"[Network] Error loading contacts: {e}")

    return contacts


# ── Path Finding ──────────────────────────────────────────────────────────────

def find_paths_to_company(contacts: list[Contact], target_company: str) -> list[PathResult]:
    """
    Find all 1st-degree contacts currently at target_company.
    Uses fuzzy company name matching (strip legal suffixes, check substring).

    Returns list of PathResult with path_length=1 for direct matches.
    Empty list if no direct match found (caller handles 2nd-degree estimation).
    """
    target_norm = _normalize(target_company)
    paths = []

    for contact in contacts:
        contact_co_norm = _normalize(contact.company)
        # Direct match OR substring in either direction
        if (contact_co_norm == target_norm or
                target_norm in contact_co_norm or
                contact_co_norm in target_norm):
            paths.append(PathResult(
                target=target_company,
                path_length=1,
                bridge_contact=contact,
                company=target_company,
            ))

    if paths:
        print(f"[Network] Found {len(paths)} direct path(s) to {target_company}")
    else:
        print(f"[Network] No direct contacts at {target_company} — 2nd-degree paths only")
    return paths


def find_paths_to_person(
    contacts: list[Contact],
    target_name: str,
    target_company: str = "",
) -> list[PathResult]:
    """
    Search contacts for target_name (fuzzy match).
    If found: direct path (length 1, this person IS the contact).
    If not found: delegate to find_paths_to_company for same-company paths.
    """
    target_norm = _normalize(target_name)
    paths = []

    for contact in contacts:
        if target_norm in _normalize(contact.full_name):
            # This person is directly in our network
            paths.append(PathResult(
                target=target_name,
                path_length=1,
                bridge_contact=contact,
                company=target_company or contact.company,
            ))

    if not paths and target_company:
        # Fall back: find contacts at same company
        company_paths = find_paths_to_company(contacts, target_company)
        # Re-label these as paths TO the person VIA a contact
        for p in company_paths:
            p.target = target_name
            paths.append(p)

    return paths


# ── Script Generation ─────────────────────────────────────────────────────────

OUTREACH_PROMPT = """You are writing a personalized outreach message on behalf of a senior executive.
The message must NOT be a template. Every sentence must be specific to this exact situation.

SENDER PROFILE:
{profile}

BRIDGE CONTACT (the person being reached out TO, or via whom the intro happens):
Name: {bridge_name}
Position: {bridge_position}
Company: {bridge_company}
Connected since: {connected_on}

TARGET CONTEXT:
{target_context}

{jd_section}

{fit_section}

Write a LinkedIn DM or email (3 short paragraphs, 120–150 words total):

PARAGRAPH 1: Establish a specific, genuine connection point with {bridge_name}.
  - Reference something specific about their background, company, or role
  - NOT: "I saw you work at...", "I noticed you're connected to...", "I hope this message finds you well"
  - DO: Reference a specific shared domain, a company challenge they'd know about, or a mutual context

PARAGRAPH 2: Why Santiago is reaching out NOW — a specific, timely reason.
  - If FIT STRENGTHS are provided above, lead with the STRONGEST one as the hook
  - Otherwise reference one concrete Santiago credential directly relevant to this person's world
    (choose the most relevant: SoyYo exit, Avianca CDTO, Uff Móvil MVNO, MIT Sloan, current AI work)
  - Make the relevance obvious — don't make them guess why he's writing

PARAGRAPH 3: A clear, low-friction ask.
  - Either: a 15-minute call to exchange perspective on [specific topic]
  - Or: a warm introduction to [specific person/role] at [company]
  - NOT: "I'd love to connect", "Let me know if you have time", "I'm exploring opportunities"

FORBIDDEN PHRASES: "hope this finds you well", "excited to", "I'm looking for opportunities",
"I believe", "I'm passionate about", "quick chat", "pick your brain"

Return ONLY valid JSON:
{{
  "script": "<full 3-paragraph message>",
  "rationale": "<2 sentences: which Santiago credential was chosen and why it fits this specific target>"
}}"""


def _analyze_jd_fit_for_outreach(jd_input: str) -> dict:
    """
    Fetch JD (if URL) and run a lightweight fit analysis.
    Returns dict with fit_strengths and fit_score, or empty dict on failure.
    """
    import httpx
    import re as _re
    from anthropic import Anthropic
    from bs4 import BeautifulSoup

    jd_text = ""
    jd_input = jd_input.strip()
    if jd_input.startswith("http://") or jd_input.startswith("https://"):
        try:
            resp = httpx.get(jd_input, timeout=12, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                jd_text = soup.get_text(separator="\n")
                jd_text = _re.sub(r'\n{3,}', '\n\n', jd_text).strip()[:3000]
        except Exception:
            return {}
    else:
        jd_text = jd_input[:3000]

    if not jd_text:
        return {}

    prompt = f"""Given this executive profile and job description, identify the 2-3 strongest credential matches.

EXECUTIVE PROFILE:
{EXECUTIVE_PROFILE}

JOB DESCRIPTION:
{jd_text}

Return ONLY valid JSON:
{{"fit_score": <0-100>, "fit_strengths": "<2-3 specific profile credentials that directly match JD requirements — be concrete, not generic>"}}"""

    try:
        client = Anthropic()
        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = _re.sub(r'^```(?:json)?\s*', '', raw)
        raw = _re.sub(r'\s*```$', '', raw)
        import json as _json
        return _json.loads(raw)
    except Exception:
        return {}


def generate_outreach_scripts(
    paths: list[PathResult],
    target_context: str = "",
    jd_snippet: str = "",
    jd_fit: dict = None,
) -> list[PathResult]:
    """
    For each PathResult, generate a personalized outreach script via Claude Opus.
    Modifies PathResult.outreach_script and PathResult.rationale in place.
    Returns updated list.
    """
    if not paths:
        return paths

    client = anthropic.Anthropic()
    jd_section = f"JOB DESCRIPTION CONTEXT:\n{jd_snippet[:500]}" if jd_snippet else ""

    # If jd_fit not pre-computed but jd_snippet looks like a URL, run fit analysis
    if jd_fit is None and jd_snippet:
        print("[Network] Running JD fit analysis for outreach angle...")
        jd_fit = _analyze_jd_fit_for_outreach(jd_snippet)
        if jd_fit.get("fit_strengths"):
            print(f"[Network] Fit score: {jd_fit.get('fit_score', 'N/A')} — using strengths as outreach hook")

    fit_section = ""
    if jd_fit and jd_fit.get("fit_strengths"):
        fit_section = f"FIT STRENGTHS (use the strongest one as Para 2 hook):\n{jd_fit['fit_strengths']}"

    for i, path in enumerate(paths):
        c = path.bridge_contact
        print(f"[Network] Generating script {i+1}/{len(paths)}: via {c.full_name} ({c.company})")

        prompt = OUTREACH_PROMPT.format(
            profile=EXECUTIVE_PROFILE,
            bridge_name=c.full_name,
            bridge_position=c.position or "professional contact",
            bridge_company=c.company,
            connected_on=c.connected_on or "unknown date",
            target_context=target_context or f"Reaching out regarding opportunities at {path.company}",
            jd_section=jd_section,
            fit_section=fit_section,
        )

        try:
            response = client.messages.create(
                model=MODEL_OPUS,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            result = json.loads(raw)
            path.outreach_script = result.get("script", "")
            path.rationale = result.get("rationale", "")
        except Exception as e:
            print(f"[Network] Script generation error for {c.full_name}: {e}")
            path.outreach_script = f"[Script generation failed: {e}]"
            path.rationale = ""

    return paths


# ── Estimated 2nd-Degree Paths ────────────────────────────────────────────────

def estimate_second_degree_paths(
    contacts: list[Contact],
    target_company: str,
    n: int = 3,
) -> list[PathResult]:
    """
    When no direct connection exists, find the most relevant adjacent contacts
    who work in the same sector and could plausibly make an intro.

    Heuristic: contacts at payments/fintech/banking companies with senior titles
    are most likely to have 2nd-degree connections into target company.
    """
    SECTOR_KEYWORDS = [
        "payments", "fintech", "banking", "finance", "financial",
        "card", "stripe", "visa", "mastercard", "paypal", "square",
        "blockchain", "crypto", "insurance", "capital",
    ]
    SENIORITY_KEYWORDS = [
        "chief", "vp", "svp", "evp", "president", "director",
        "head of", "managing", "partner", "founder", "cto", "cpo", "ceo"
    ]

    candidates = []
    for contact in contacts:
        co_norm = _normalize(contact.company)
        pos_norm = contact.position.lower()
        sector_score = sum(1 for kw in SECTOR_KEYWORDS if kw in co_norm or kw in pos_norm)
        seniority_score = sum(1 for kw in SENIORITY_KEYWORDS if kw in pos_norm)
        if sector_score > 0 and seniority_score > 0:
            candidates.append((sector_score + seniority_score, contact))

    candidates.sort(reverse=True, key=lambda x: x[0])
    paths = []
    for _, contact in candidates[:n]:
        paths.append(PathResult(
            target=target_company,
            path_length=2,
            bridge_contact=contact,
            company=target_company,
        ))

    if paths:
        print(f"[Network] Estimated {len(paths)} 2nd-degree path(s) via adjacent contacts")
    return paths


# ── Report Formatter ──────────────────────────────────────────────────────────

def format_report(paths: list[PathResult], target: str) -> str:
    lines = [
        f"# Network Pathfinder — {target}",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        f"_Paths found: {len(paths)}_",
        "",
    ]

    direct = [p for p in paths if p.path_length == 1]
    estimated = [p for p in paths if p.path_length == 2]

    if direct:
        lines.append("## Direct Paths (1st Degree)")
        for p in direct:
            c = p.bridge_contact
            lines += [
                f"\n### Via {c.full_name}",
                f"- **Path**: Santiago → {c.full_name} → {p.target}",
                f"- **Bridge Contact**: {c.full_name}, {c.position} at {c.company}",
                f"- **Connected Since**: {c.connected_on or 'Unknown'}",
                "",
                "**Outreach Script**:",
                "",
                p.outreach_script or "_Not generated_",
                "",
                f"**Rationale**: {p.rationale or '_Not generated_'}",
                "",
                "---",
            ]

    if estimated:
        lines.append("\n## Estimated 2nd-Degree Paths (via adjacent contacts)")
        lines.append("_These contacts work in adjacent fintech/payments companies and likely have 2nd-degree connections into the target._")
        lines.append("")
        for p in estimated:
            c = p.bridge_contact
            lines += [
                f"\n### Via {c.full_name} ({c.company})",
                f"- **Path**: Santiago → {c.full_name} → [2nd degree] → {p.target}",
                f"- **Bridge Contact**: {c.full_name}, {c.position} at {c.company}",
                "",
                "**Outreach Script** (ask for intro to {p.target}):",
                "",
                p.outreach_script or "_Not generated_",
                "",
                f"**Rationale**: {p.rationale or '_Not generated_'}",
                "",
                "---",
            ]

    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run(
    target: str,
    contacts_csv: Path = None,
    target_context: str = "",
    jd_snippet: str = "",
    jd_fit: dict = None,
    is_company: bool = True,
    target_person_company: str = "",
    generate_scripts: bool = True,
    n_second_degree: int = 3,
) -> str:
    """
    Main entry point for Module 4.

    Args:
        target: Company name (if is_company=True) or person name
        contacts_csv: Path to LinkedIn contacts CSV export
        target_context: Free-text description of target (who they are, why reaching out)
        jd_snippet: Optional JD text to inform outreach angle
        is_company: True = search by company, False = search by person name
        target_person_company: Company where target person works (for person search)
        generate_scripts: Whether to call Claude for outreach scripts
        n_second_degree: Number of estimated 2nd-degree paths to generate if no direct found

    Returns:
        Markdown report string.
    """
    if contacts_csv is None:
        contacts_csv = CONTACTS_CSV

    # 1. Load contacts
    contacts = load_contacts(contacts_csv)
    if not contacts:
        return f"[Network Pathfinder] No contacts loaded. Provide a LinkedIn contacts CSV at {contacts_csv}"

    # 2. Find paths
    if is_company:
        paths = find_paths_to_company(contacts, target)
    else:
        paths = find_paths_to_person(contacts, target, target_person_company)

    # 3. Fall back to 2nd-degree if no direct paths
    if not paths:
        company_for_2nd = target if is_company else target_person_company
        paths = estimate_second_degree_paths(contacts, company_for_2nd, n=n_second_degree)
        if not paths:
            return f"[Network Pathfinder] No paths found to '{target}'. Expand contacts CSV or try a different target."

    # 4. Generate scripts
    if generate_scripts:
        paths = generate_outreach_scripts(paths, target_context, jd_snippet, jd_fit=jd_fit)

    # 5. Format + save
    report = format_report(paths, target)
    report_path = DATA_DIR / "outreach_scripts.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[Network] Report saved to {report_path}")

    # Cache paths as JSON
    cache_path = DATA_DIR / "network_paths.json"
    cache_data = []
    for p in paths:
        d = asdict(p)
        cache_data.append(d)
    cache_path.write_text(json.dumps(cache_data, indent=2, default=str), encoding="utf-8")

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="Network Pathfinder — map paths to target companies/people and generate outreach scripts"
    )
    parser.add_argument("--target", required=True,
                        help="Target company name or person name")
    parser.add_argument("--contacts", type=Path, default=None,
                        help="Path to LinkedIn contacts CSV export")
    parser.add_argument("--context", default="",
                        help="Free-text context about the target (who they are, why reaching out)")
    parser.add_argument("--jd", default="",
                        help="Job description text or URL for outreach context")
    parser.add_argument("--person", action="store_true",
                        help="Search by person name instead of company")
    parser.add_argument("--company", default="",
                        help="Company where target person works (use with --person)")
    parser.add_argument("--no-scripts", action="store_true",
                        help="Skip Claude script generation")
    args = parser.parse_args()

    report = run(
        target=args.target,
        contacts_csv=args.contacts,
        target_context=args.context,
        jd_snippet=args.jd,
        is_company=not args.person,
        target_person_company=args.company,
        generate_scripts=not args.no_scripts,
    )
    print("\n" + "="*60)
    print(report)
