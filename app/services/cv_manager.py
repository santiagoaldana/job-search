"""
CV Manager — canonical JSON CV, chat-driven edits, multi-format export.
Source of truth: cv/master_cv.json
Versions: cv/versions/<slug>.json
"""

import json
import re
import copy
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

BASE_DIR = Path(__file__).parent.parent.parent
MASTER_CV_PATH = BASE_DIR / "cv" / "master_cv.json"
VERSIONS_DIR = BASE_DIR / "cv" / "versions"
CV_OUTPUT_DIR = BASE_DIR / "cv" / "output"

VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
CV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Pending diffs awaiting approval (in-memory; keyed by version_name)
_pending_diffs: dict = {}


def load_master_cv() -> dict:
    return json.loads(MASTER_CV_PATH.read_text())


def load_version(version_name: str) -> dict:
    path = VERSIONS_DIR / f"{version_name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return load_master_cv()


def list_cv_versions() -> list:
    return [p.stem for p in sorted(VERSIONS_DIR.glob("*.json"))]


def _version_slug(version_name: Optional[str]) -> str:
    if not version_name:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
        return f"version_{ts}"
    return re.sub(r"[^a-z0-9_-]", "_", version_name.lower())


async def chat_edit_cv(
    instruction: str,
    lead_id: Optional[int] = None,
    version_name: Optional[str] = None,
) -> dict:
    """
    Natural language CV edit via Claude Opus.
    Returns: {diff: [{section, original, proposed}], version_name: str, pending_cv: dict}
    """
    client = anthropic.Anthropic()
    master = load_master_cv()

    jd_context = ""
    if lead_id:
        try:
            from app.database import engine
            from sqlmodel import Session
            from app.models import Lead
            with Session(engine) as session:
                lead = session.get(Lead, lead_id)
                if lead:
                    jd_context = f"\nJob Title: {lead.title}\nLocation: {lead.location}\nJD: {(lead.description or '')[:2000]}"
        except Exception:
            pass

    prompt = f"""You are helping Santiago Aldana tailor his executive CV.

CURRENT CV (JSON):
{json.dumps(master, indent=2)[:4000]}

EDIT INSTRUCTION: {instruction}
{jd_context}

CONSTRAINTS:
- Never fabricate metrics, dates, company names, or titles not in the original
- Reorder experience bullets by relevance to the target role
- Reframe language using the job's vocabulary where authentic
- Keep the summary to 3-4 sentences

Return ONLY valid JSON (no markdown fences) with this structure:
{{
  "summary": "<new summary or same if unchanged>",
  "competencies": ["<competency>"],
  "experience": [
    {{
      "company": "<unchanged>",
      "title": "<unchanged>",
      "location": "<unchanged>",
      "dates": "<unchanged>",
      "bullets": ["<reframed or same bullet>"],
      "accomplishment": "<unchanged>"
    }}
  ],
  "changes_explanation": "<2-3 sentences explaining what changed and why>"
}}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    proposed = json.loads(raw)

    # Build diff
    diff = []
    for section in ["summary", "competencies"]:
        orig = master.get(section)
        prop = proposed.get(section)
        if orig != prop:
            diff.append({"section": section, "original": orig, "proposed": prop})

    for i, (orig_exp, prop_exp) in enumerate(
        zip(master.get("experience", []), proposed.get("experience", []))
    ):
        if orig_exp.get("bullets") != prop_exp.get("bullets"):
            diff.append({
                "section": f"experience[{i}]",
                "company": orig_exp.get("company"),
                "original": orig_exp.get("bullets"),
                "proposed": prop_exp.get("bullets"),
            })

    slug = _version_slug(version_name)

    # Build the full pending CV (merge master with proposed changes)
    pending_cv = copy.deepcopy(master)
    pending_cv["summary"] = proposed.get("summary", master["summary"])
    pending_cv["competencies"] = proposed.get("competencies", master["competencies"])
    pending_cv["experience"] = proposed.get("experience", master["experience"])

    _pending_diffs[slug] = {
        "diff": diff,
        "pending_cv": pending_cv,
        "changes_explanation": proposed.get("changes_explanation", ""),
    }

    return {
        "diff": diff,
        "version_name": slug,
        "changes_explanation": proposed.get("changes_explanation", ""),
    }


async def apply_approved_diff(version_name: str, approved_sections: list) -> Path:
    """
    Apply only the approved sections from the pending diff and save as a version.
    approved_sections: list of section names (e.g. ["summary", "experience[0]"])
    """
    pending = _pending_diffs.get(version_name)
    if not pending:
        raise ValueError(f"No pending diff for version '{version_name}'")

    master = load_master_cv()
    result = copy.deepcopy(master)

    for change in pending["diff"]:
        section = change["section"]
        if section not in approved_sections:
            continue
        if section == "summary":
            result["summary"] = change["proposed"]
        elif section == "competencies":
            result["competencies"] = change["proposed"]
        elif section.startswith("experience["):
            idx = int(re.search(r'\[(\d+)\]', section).group(1))
            result["experience"][idx]["bullets"] = change["proposed"]

    path = VERSIONS_DIR / f"{version_name}.json"
    path.write_text(json.dumps(result, indent=2))
    del _pending_diffs[version_name]
    return path


async def synthesize_for_lead(lead, company_name: str, version_name: Optional[str] = None) -> dict:
    """Generate a tailored CV version for a specific lead."""
    instruction = (
        f"Tailor this CV for the role of '{lead.title}' at {company_name}. "
        f"Reorder bullets to lead with the most relevant experience. "
        f"Use the JD's vocabulary where authentic."
    )
    return await chat_edit_cv(
        instruction=instruction,
        lead_id=lead.id,
        version_name=version_name or f"{company_name}_{lead.title}".replace(" ", "_")[:40],
    )


def export_cv(format: str = "pdf", version_name: Optional[str] = None) -> Path:
    """Export CV in the requested format. Returns path to the output file."""
    cv_data = load_version(version_name) if version_name else load_master_cv()
    slug = version_name or "master"
    ts = datetime.utcnow().strftime("%Y%m%d")

    if format == "plaintext":
        return _export_plaintext(cv_data, slug, ts)
    elif format == "html":
        return _export_html(cv_data, slug, ts)
    else:
        return _export_pdf(cv_data, slug, ts)


def _export_plaintext(cv: dict, slug: str, ts: str) -> Path:
    """ATS-safe plain text — no tables, no columns, standard headers."""
    lines = []
    c = cv.get("contact", {})
    lines += [
        cv.get("name", "Santiago Aldana"),
        f"{c.get('phone','')} | {c.get('email','')} | {c.get('linkedin','')} | {c.get('location','')}",
        "",
        "EXECUTIVE SUMMARY",
        cv.get("summary", ""),
        "",
        "CORE COMPETENCIES",
        " | ".join(cv.get("competencies", [])),
        "",
        "PROFESSIONAL EXPERIENCE",
    ]
    for exp in cv.get("experience", []):
        lines += [
            f"{exp['title']}, {exp['company']} | {exp.get('location','')} | {exp.get('dates','')}",
        ]
        for bullet in exp.get("bullets", []):
            lines.append(f"- {bullet}")
        if exp.get("accomplishment"):
            lines.append(f"Accomplishment: {exp['accomplishment']}")
        lines.append("")

    if cv.get("previous_experience"):
        lines += ["ADDITIONAL EXPERIENCE"]
        for pe in cv["previous_experience"]:
            lines.append(f"- {pe['title']}, {pe['company']}: {pe.get('summary','')}")
        lines.append("")

    lines += ["BOARD & ADVISORY"]
    for b in cv.get("board", []):
        lines.append(f"- {b['role']}, {b['company']} ({b.get('dates','')}): {b.get('summary','')}")
    lines.append("")

    lines += ["EDUCATION"]
    for e in cv.get("education", []):
        lines.append(f"- {e['degree']}, {e['institution']}, {e.get('location','')}")
    lines.append("")

    add = cv.get("additional", {})
    if add:
        lines += [
            "ADDITIONAL INFORMATION",
            f"Languages: {add.get('languages','')}",
            f"Work Authorization: {add.get('work_authorization','')}",
        ]

    path = CV_OUTPUT_DIR / f"{slug}_{ts}.txt"
    path.write_text("\n".join(lines))
    return path


def _export_html(cv: dict, slug: str, ts: str) -> Path:
    """Simple HTML CV."""
    c = cv.get("contact", {})
    exp_html = ""
    for exp in cv.get("experience", []):
        bullets = "".join(f"<li>{b}</li>" for b in exp.get("bullets", []))
        exp_html += f"""
        <div class="job">
          <h3>{exp['title']} — {exp['company']}</h3>
          <p class="meta">{exp.get('location','')} | {exp.get('dates','')}</p>
          <ul>{bullets}</ul>
        </div>"""

    board_html = "".join(
        f"<li><strong>{b['company']}</strong> ({b.get('dates','')}): {b.get('summary','')}</li>"
        for b in cv.get("board", [])
    )
    edu_html = "".join(
        f"<li>{e['degree']}, {e['institution']}</li>"
        for e in cv.get("education", [])
    )
    comp_html = " &bull; ".join(cv.get("competencies", []))

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>{cv.get('name','Santiago Aldana')} — CV</title>
<style>
  body{{font-family:Georgia,serif;max-width:800px;margin:40px auto;color:#222;line-height:1.5}}
  h1{{font-size:2em;margin-bottom:4px}} h2{{border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:24px}}
  h3{{margin-bottom:2px}} .meta{{color:#666;font-size:.9em;margin:0}} ul{{margin-top:6px}}
  .competencies{{background:#f5f5f5;padding:10px;border-radius:4px}}
</style></head><body>
<h1>{cv.get('name','Santiago Aldana')}</h1>
<p>{c.get('phone','')} | <a href="mailto:{c.get('email','')}">{c.get('email','')}</a> |
   <a href="https://{c.get('linkedin','')}">{c.get('linkedin','')}</a> | {c.get('location','')}</p>
<h2>Executive Summary</h2><p>{cv.get('summary','')}</p>
<h2>Core Competencies</h2><p class="competencies">{comp_html}</p>
<h2>Professional Experience</h2>{exp_html}
<h2>Board &amp; Advisory</h2><ul>{board_html}</ul>
<h2>Education</h2><ul>{edu_html}</ul>
</body></html>"""

    path = CV_OUTPUT_DIR / f"{slug}_{ts}.html"
    path.write_text(html)
    return path


def _export_pdf(cv: dict, slug: str, ts: str) -> Path:
    """2-page PDF via reportlab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    path = CV_OUTPUT_DIR / f"{slug}_{ts}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=LETTER,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)

    styles = getSampleStyleSheet()
    DARK = colors.HexColor("#1a1a2e")
    ACCENT = colors.HexColor("#16213e")

    name_style = ParagraphStyle("Name", fontSize=18, textColor=DARK,
                                spaceAfter=2, alignment=TA_CENTER, fontName="Helvetica-Bold")
    contact_style = ParagraphStyle("Contact", fontSize=9, textColor=ACCENT,
                                   spaceAfter=6, alignment=TA_CENTER)
    h2_style = ParagraphStyle("H2", fontSize=10, textColor=DARK, spaceBefore=8,
                               spaceAfter=2, fontName="Helvetica-Bold")
    body_style = ParagraphStyle("Body", fontSize=9, spaceAfter=2, leading=12)
    bullet_style = ParagraphStyle("Bullet", fontSize=9, spaceAfter=1,
                                  leading=12, leftIndent=12, bulletIndent=0)

    c = cv.get("contact", {})
    story = [
        Paragraph(cv.get("name", "Santiago Aldana"), name_style),
        Paragraph(
            f"{c.get('phone','')} | {c.get('email','')} | "
            f"{c.get('linkedin','')} | {c.get('location','')}",
            contact_style,
        ),
        HRFlowable(width="100%", thickness=1, color=DARK, spaceAfter=4),
        Paragraph("EXECUTIVE SUMMARY", h2_style),
        Paragraph(cv.get("summary", ""), body_style),
        Paragraph("CORE COMPETENCIES", h2_style),
        Paragraph(" • ".join(cv.get("competencies", [])), body_style),
        Paragraph("PROFESSIONAL EXPERIENCE", h2_style),
    ]

    for exp in cv.get("experience", []):
        story.append(Paragraph(
            f"<b>{exp['title']}</b>, {exp['company']} | "
            f"{exp.get('location','')} | {exp.get('dates','')}",
            body_style,
        ))
        for b in exp.get("bullets", []):
            story.append(Paragraph(f"• {b}", bullet_style))
        story.append(Spacer(1, 4))

    if cv.get("board"):
        story.append(Paragraph("BOARD & ADVISORY", h2_style))
        for b in cv["board"]:
            story.append(Paragraph(
                f"<b>{b['company']}</b> ({b.get('dates','')}): {b.get('summary','')}",
                bullet_style,
            ))

    if cv.get("education"):
        story.append(Paragraph("EDUCATION", h2_style))
        for e in cv["education"]:
            story.append(Paragraph(f"{e['degree']}, {e['institution']}", bullet_style))

    doc.build(story)
    return path
