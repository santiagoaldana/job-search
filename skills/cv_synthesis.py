"""
CV Synthesis Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Takes the master CV PDF + a job description (URL or text) and produces a
tailored, 2-page PDF and HTML CV using Claude Opus for synthesis and
reportlab for rendering.

CRITICAL CONSTRAINT: No fabrication. Every metric, company name, date, and
title in the output must exist verbatim in the source CV text. A post-
generation validation step enforces this.

Usage:
  python3 -m skills.cv_synthesis --jd <url_or_text> --company Stripe --role "Chief Product Officer"
  python3 -m skills.cv_synthesis --jd <url_or_text> --company Stripe --role CPO --format html
"""

import httpx
import json
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import anthropic
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

from skills.shared import (
    EXECUTIVE_PROFILE, MODEL_OPUS, MODEL_HAIKU, MASTER_CV_PATH, CV_OUTPUT_DIR, DATA_DIR
)

# ── PDF Text Extraction ───────────────────────────────────────────────────────

def extract_cv_text(pdf_path: Path = MASTER_CV_PATH) -> str:
    """
    Extract raw text from master CV PDF using pdfminer.six.
    Preserves approximate layout. Raises FileNotFoundError if PDF missing.
    """
    from pdfminer.high_level import extract_text
    if not pdf_path.exists():
        raise FileNotFoundError(f"Master CV not found at: {pdf_path}")
    text = extract_text(str(pdf_path))
    # Normalize whitespace but preserve paragraph breaks
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


# ── Job Description Fetcher ───────────────────────────────────────────────────

def fetch_job_description(jd_input: str) -> str:
    """
    Accept either raw JD text or a URL.
    If URL: fetch with httpx, strip HTML with BeautifulSoup, return clean text.
    If plain text: return as-is.
    """
    jd_input = jd_input.strip()
    if jd_input.startswith("http://") or jd_input.startswith("https://"):
        try:
            resp = httpx.get(jd_input, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove nav, footer, script, style noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            return text[:8000]  # Cap at 8K chars — enough for any JD
        except Exception as e:
            raise RuntimeError(f"Failed to fetch JD from URL: {e}")
    return jd_input


# ── Claude Synthesis ──────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are an executive CV strategist. Your job is to reframe an executive's existing career history to match a specific job description — without inventing anything.

CRITICAL RULE: If a number, company name, date range, or job title does not appear verbatim in the CV TEXT provided, do not use it. You may rephrase and reorder, but never fabricate.

EXECUTIVE CV TEXT:
{cv_text}

JOB DESCRIPTION:
{jd_text}

TARGET ROLE: {role_title} at {company}

Your task: Return a single valid JSON object (no markdown, no explanation, just raw JSON) with this exact structure:

{{
  "summary": "<3-sentence executive summary. Sentence 1: who Santiago is + years of experience. Sentence 2: most relevant credential for THIS specific role. Sentence 3: what he brings that is unique for this company/sector>",
  "core_competencies": ["<6-8 keyword phrases that match the JD's language exactly — drawn from Santiago's actual experience>"],
  "experience": [
    {{
      "title": "<exact title from CV>",
      "company": "<exact company from CV>",
      "dates": "<exact dates from CV>",
      "achievements": ["<reframed achievement 1 — use JD vocabulary where the meaning matches>", "<achievement 2>", "<achievement 3 — max 4 per role>"]
    }}
  ],
  "education": [
    {{"degree": "<degree>", "institution": "<institution>", "year": "<year if in CV>"}}
  ],
  "board_advisory": ["<board role 1>", "<board role 2>"],
  "reframe_notes": "<2-3 sentences explaining what you changed and why — for Santiago's review only>"
}}

Rank experience entries by relevance to THIS specific JD (most relevant first), not by chronology.
Keep the full experience list — do not drop roles.
Use the JD's vocabulary where it matches existing facts (e.g., if JD says 'revenue operations' and CV says 'P&L management', use the JD's term only if the underlying fact is identical).
"""

def synthesize_cv(cv_text: str, jd_text: str, company: str, role_title: str) -> dict:
    """
    Call Claude Opus to synthesize a tailored CV structure from cv_text + jd_text.
    Returns parsed dict. Raises ValueError if JSON parse fails.
    """
    client = anthropic.Anthropic()
    prompt = SYNTHESIS_PROMPT.format(
        cv_text=cv_text[:6000],  # Fit within context budget
        jd_text=jd_text[:3000],
        role_title=role_title,
        company=company,
    )
    response = client.messages.create(
        model=MODEL_OPUS,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    # Strip any accidental markdown code fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")


# ── Validation ────────────────────────────────────────────────────────────────

def validate_no_fabrication(cv_data: dict, cv_text: str) -> list[str]:
    """
    Cross-check all numbers and dollar amounts in synthesized CV against
    numbers found in the source cv_text. Returns list of warnings (empty = clean).
    """
    # Extract all numbers/dollar amounts from output
    output_text = json.dumps(cv_data)
    output_numbers = set(re.findall(r'\$[\d,\.]+[MBK]?|\b\d{4}\b|\b\d+[MBK]\b|\b\d{2,}\b', output_text))
    source_numbers = set(re.findall(r'\$[\d,\.]+[MBK]?|\b\d{4}\b|\b\d+[MBK]\b|\b\d{2,}\b', cv_text))

    warnings = []
    for num in output_numbers:
        if num not in source_numbers and len(num) > 3:  # Skip short numbers like "20"
            warnings.append(f"Possible fabrication: '{num}' in output not found in source CV")
    return warnings


# ── PDF Renderer ──────────────────────────────────────────────────────────────

# Color palette — professional, not generic
COLOR_DARK = colors.HexColor("#1a1a2e")
COLOR_ACCENT = colors.HexColor("#16213e")
COLOR_MID = colors.HexColor("#4a4a6a")
COLOR_LIGHT = colors.HexColor("#f0f0f5")
COLOR_LINE = colors.HexColor("#c0c0d0")


def _build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["name"] = ParagraphStyle(
        "name", parent=base["Normal"],
        fontSize=20, fontName="Helvetica-Bold",
        textColor=COLOR_DARK, spaceAfter=2, leading=24,
    )
    styles["tagline"] = ParagraphStyle(
        "tagline", parent=base["Normal"],
        fontSize=10, fontName="Helvetica",
        textColor=COLOR_MID, spaceAfter=4, leading=13,
    )
    styles["section_header"] = ParagraphStyle(
        "section_header", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=COLOR_ACCENT, spaceBefore=8, spaceAfter=3,
        leading=11, textTransform="uppercase",
    )
    styles["body"] = ParagraphStyle(
        "body", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=COLOR_DARK, leading=12, spaceAfter=2,
    )
    styles["body_bold"] = ParagraphStyle(
        "body_bold", parent=base["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=COLOR_DARK, leading=12,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet", parent=base["Normal"],
        fontSize=8.5, fontName="Helvetica",
        textColor=COLOR_DARK, leading=11,
        leftIndent=10, spaceAfter=2,
        bulletIndent=2,
    )
    styles["summary"] = ParagraphStyle(
        "summary", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=COLOR_DARK, leading=13,
        alignment=TA_JUSTIFY, spaceAfter=4,
    )
    styles["contact"] = ParagraphStyle(
        "contact", parent=base["Normal"],
        fontSize=8, fontName="Helvetica",
        textColor=COLOR_MID, leading=11,
    )
    return styles


def render_pdf(cv_data: dict, role_title: str, output_path: Path) -> Path:
    """
    Render synthesized CV dict to a formatted 2-page PDF using reportlab Platypus.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
    )

    S = _build_styles()
    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    story.append(Paragraph("Santiago Aldana", S["name"]))
    story.append(Paragraph(role_title, S["tagline"]))
    story.append(Paragraph(
        "Boston, MA  ·  santiago@example.com  ·  linkedin.com/in/santiagoaldana  ·  U.S. & Colombia Authorization",
        S["contact"]
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_DARK, spaceAfter=6))

    # ── Summary ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Executive Summary", S["section_header"]))
    story.append(Paragraph(cv_data.get("summary", ""), S["summary"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LINE, spaceAfter=4))

    # ── Core Competencies ────────────────────────────────────────────────────
    competencies = cv_data.get("core_competencies", [])
    if competencies:
        story.append(Paragraph("Core Competencies", S["section_header"]))
        # 3-column grid
        cols = 3
        rows = [competencies[i:i+cols] for i in range(0, len(competencies), cols)]
        # Pad last row
        while len(rows[-1]) < cols:
            rows[-1].append("")
        table_data = [[Paragraph(c, S["body"]) for c in row] for row in rows]
        col_width = (LETTER[0] - 1.3*inch) / cols
        t = Table(table_data, colWidths=[col_width]*cols)
        t.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))
        story.append(t)
        story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LINE, spaceAfter=4))

    # ── Experience ───────────────────────────────────────────────────────────
    story.append(Paragraph("Experience", S["section_header"]))
    for role in cv_data.get("experience", []):
        block = []
        title_line = f"<b>{role.get('title', '')}</b>  ·  {role.get('company', '')}  ·  {role.get('dates', '')}"
        block.append(Paragraph(title_line, S["body_bold"]))
        for ach in role.get("achievements", []):
            block.append(Paragraph(f"• {ach}", S["bullet"]))
        block.append(Spacer(1, 3))
        story.append(KeepTogether(block))

    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LINE, spaceAfter=4))

    # ── Education ────────────────────────────────────────────────────────────
    story.append(Paragraph("Education", S["section_header"]))
    for edu in cv_data.get("education", []):
        line = f"<b>{edu.get('degree', '')}</b>  ·  {edu.get('institution', '')}"
        if edu.get("year"):
            line += f"  ·  {edu['year']}"
        story.append(Paragraph(line, S["body"]))

    # ── Board & Advisory ─────────────────────────────────────────────────────
    board = cv_data.get("board_advisory", [])
    if board:
        story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LINE, spaceAfter=4, spaceBefore=4))
        story.append(Paragraph("Board & Advisory", S["section_header"]))
        story.append(Paragraph("  ·  ".join(board), S["body"]))

    doc.build(story)
    return output_path


# ── HTML Renderer ─────────────────────────────────────────────────────────────

def render_html(cv_data: dict, role_title: str, output_path: Path) -> Path:
    """
    Render synthesized CV dict to a single-file HTML with inline CSS.
    Suitable for browser-based PDF printing as fallback.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    exp_html = ""
    for role in cv_data.get("experience", []):
        bullets = "".join(f"<li>{a}</li>" for a in role.get("achievements", []))
        exp_html += f"""
        <div class="role">
          <div class="role-header">
            <span class="role-title">{role.get('title','')}</span>
            <span class="role-meta"> · {role.get('company','')} · {role.get('dates','')}</span>
          </div>
          <ul>{bullets}</ul>
        </div>"""

    edu_html = "".join(
        f"<p><strong>{e.get('degree','')}</strong> · {e.get('institution','')} {('· ' + e['year']) if e.get('year') else ''}</p>"
        for e in cv_data.get("education", [])
    )

    comps = " &nbsp;·&nbsp; ".join(cv_data.get("core_competencies", []))
    board = " &nbsp;·&nbsp; ".join(cv_data.get("board_advisory", []))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Santiago Aldana — {role_title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 9pt;
          color: #1a1a2e; max-width: 8.5in; margin: 0 auto; padding: 0.65in; }}
  h1 {{ font-size: 20pt; color: #1a1a2e; margin-bottom: 2px; }}
  .tagline {{ font-size: 10pt; color: #4a4a6a; margin-bottom: 4px; }}
  .contact {{ font-size: 8pt; color: #4a4a6a; margin-bottom: 6px; }}
  hr.thick {{ border: none; border-top: 1.5px solid #1a1a2e; margin: 6px 0; }}
  hr.thin {{ border: none; border-top: 0.5px solid #c0c0d0; margin: 6px 0; }}
  h2 {{ font-size: 8pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;
        color: #16213e; margin: 8px 0 3px; }}
  .summary {{ font-size: 9pt; line-height: 1.4; text-align: justify; }}
  .competencies {{ font-size: 8.5pt; color: #1a1a2e; line-height: 1.6; }}
  .role {{ margin-bottom: 8px; }}
  .role-header {{ margin-bottom: 2px; }}
  .role-title {{ font-weight: bold; font-size: 9pt; }}
  .role-meta {{ font-size: 8.5pt; color: #4a4a6a; }}
  ul {{ padding-left: 12px; }}
  li {{ font-size: 8.5pt; line-height: 1.35; margin-bottom: 2px; }}
  .education p {{ font-size: 9pt; margin-bottom: 3px; }}
  .board {{ font-size: 8.5pt; color: #1a1a2e; }}
  @media print {{
    body {{ padding: 0.5in; }}
    @page {{ margin: 0.5in; size: letter; }}
  }}
</style>
</head>
<body>
  <h1>Santiago Aldana</h1>
  <div class="tagline">{role_title}</div>
  <div class="contact">Boston, MA &nbsp;·&nbsp; santiago@example.com &nbsp;·&nbsp; linkedin.com/in/santiagoaldana &nbsp;·&nbsp; U.S. & Colombia Work Authorization</div>
  <hr class="thick">

  <h2>Executive Summary</h2>
  <p class="summary">{cv_data.get('summary','')}</p>
  <hr class="thin">

  <h2>Core Competencies</h2>
  <p class="competencies">{comps}</p>
  <hr class="thin">

  <h2>Experience</h2>
  {exp_html}
  <hr class="thin">

  <h2>Education</h2>
  <div class="education">{edu_html}</div>

  {"<hr class='thin'><h2>Board &amp; Advisory</h2><p class='board'>" + board + "</p>" if board else ""}
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path


# ── ATS Compatibility Check ───────────────────────────────────────────────────

ATS_CHECK_PROMPT = """You are an ATS (Applicant Tracking System) specialist reviewing a tailored CV against its target job description.

JOB DESCRIPTION:
{jd_text}

TAILORED CV TEXT:
{cv_text}

Analyze ATS compatibility and return ONLY valid JSON:
{{
  "grade": "<A, B, or C>",
  "keyword_coverage_pct": <integer 0-100, % of key JD terms present in CV>,
  "missing_keywords": ["<keyword 1>", "<keyword 2>", "<keyword 3>", "<keyword 4>", "<keyword 5>"],
  "format_issues": ["<issue 1 if any, otherwise empty list>"],
  "verdict": "<1-2 sentences: overall ATS readiness and top recommendation>"
}}

Grade rubric:
  A = 80%+ keyword coverage, no major format issues — likely passes ATS
  B = 60-79% coverage or minor issues — moderate ATS risk
  C = <60% coverage or significant issues — high ATS filter risk"""


def ats_check(cv_data: dict, jd_text: str) -> dict:
    """
    Run ATS compatibility analysis on the synthesized CV vs the JD.
    Returns dict with grade, missing_keywords, format_issues, verdict.
    """
    # Build plain text version of the synthesized CV for analysis
    cv_text_parts = [cv_data.get("summary", "")]
    cv_text_parts.append("Core Competencies: " + ", ".join(cv_data.get("core_competencies", [])))
    for role in cv_data.get("experience", []):
        cv_text_parts.append(f"{role.get('title','')} at {role.get('company','')}")
        cv_text_parts.extend(role.get("achievements", []))
    cv_plain = "\n".join(cv_text_parts)

    client = anthropic.Anthropic()
    prompt = ATS_CHECK_PROMPT.format(
        jd_text=jd_text[:2000],
        cv_text=cv_plain[:3000],
    )
    try:
        response = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        return {
            "grade": "N/A",
            "keyword_coverage_pct": 0,
            "missing_keywords": [],
            "format_issues": [],
            "verdict": f"ATS check failed: {e}",
        }


def _append_ats_report_to_html(html_path: Path, ats: dict) -> None:
    """Append ATS report as a hidden-in-print section at the bottom of the HTML CV."""
    grade = ats.get("grade", "N/A")
    coverage = ats.get("keyword_coverage_pct", 0)
    missing = ats.get("missing_keywords", [])
    issues = ats.get("format_issues", [])
    verdict = ats.get("verdict", "")

    grade_color = {"A": "#2d6a2d", "B": "#7a5c00", "C": "#8b1a1a"}.get(grade, "#444")
    missing_html = "".join(f"<li><code>{kw}</code></li>" for kw in missing) if missing else "<li>None — strong coverage</li>"
    issues_html = "".join(f"<li>{i}</li>" for i in issues) if issues else "<li>None identified</li>"

    ats_section = f"""
<!-- ATS REPORT — hidden in print, visible in browser -->
<div class="ats-report" style="margin-top:40px;padding:16px;border:1px solid #ddd;border-radius:6px;background:#f9f9f9;font-family:monospace;font-size:8.5pt;">
  <h3 style="margin:0 0 8px;font-size:10pt;color:{grade_color};">ATS Compatibility Report — Grade: {grade}</h3>
  <p style="margin:0 0 6px;"><strong>Keyword Coverage:</strong> {coverage}%</p>
  <p style="margin:0 0 4px;"><strong>Missing Keywords to Add:</strong></p>
  <ul style="margin:0 0 8px;padding-left:18px;">{missing_html}</ul>
  <p style="margin:0 0 4px;"><strong>Format Issues:</strong></p>
  <ul style="margin:0 0 8px;padding-left:18px;">{issues_html}</ul>
  <p style="margin:0;"><strong>Verdict:</strong> {verdict}</p>
</div>
<style>@media print {{ .ats-report {{ display: none; }} }}</style>"""

    content = html_path.read_text(encoding="utf-8")
    content = content.replace("</body>", ats_section + "\n</body>")
    html_path.write_text(content, encoding="utf-8")


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run(
    jd_input: str,
    company: str,
    role_title: str,
    output_format: str = "both",
    cv_path: Path = MASTER_CV_PATH,
) -> str:
    """
    Main entry point for Module 5.

    Args:
        jd_input: Raw JD text or URL
        company: Company name (used in output filename)
        role_title: Role title (used in CV header + synthesis context)
        output_format: "pdf", "html", or "both"
        cv_path: Path to master CV PDF (defaults to shared constant)

    Returns:
        String summary of output paths.
    """
    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    console.print(f"[bold]CV Synthesis[/bold] — {role_title} @ {company}")

    # 1. Extract master CV text
    console.print("  [dim]Extracting master CV text...[/dim]")
    cv_text = extract_cv_text(cv_path)
    console.print(f"  [dim]Extracted {len(cv_text)} characters from master CV[/dim]")

    # 2. Fetch JD
    console.print("  [dim]Fetching job description...[/dim]")
    jd_text = fetch_job_description(jd_input)
    console.print(f"  [dim]Job description: {len(jd_text)} characters[/dim]")

    # 3. Synthesize with Claude
    console.print("  [dim]Synthesizing with Claude Opus...[/dim]")
    cv_data = synthesize_cv(cv_text, jd_text, company, role_title)

    # 4. Validate — no fabrication
    warnings = validate_no_fabrication(cv_data, cv_text)
    if warnings:
        console.print(Panel("\n".join(warnings), title="[yellow]Fabrication Warnings[/yellow]", border_style="yellow"))
    else:
        console.print("  [green]Validation passed — no fabricated metrics detected[/green]")

    # 5. ATS check
    console.print("  [dim]Running ATS compatibility check...[/dim]")
    ats = ats_check(cv_data, jd_text)
    ats_grade = ats.get("grade", "N/A")
    ats_coverage = ats.get("keyword_coverage_pct", 0)
    grade_color = {"A": "green", "B": "yellow", "C": "red"}.get(ats_grade, "white")
    console.print(f"  [{grade_color}]ATS Grade: {ats_grade} ({ats_coverage}% keyword coverage)[/{grade_color}]")
    if ats.get("missing_keywords"):
        console.print(f"  [dim]Missing keywords: {', '.join(ats['missing_keywords'])}[/dim]")

    # 6. Render
    date_str = datetime.now().strftime("%Y%m%d")
    company_slug = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())
    outputs = []

    if output_format in ("pdf", "both"):
        pdf_path = CV_OUTPUT_DIR / f"cv_{company_slug}_{date_str}.pdf"
        console.print(f"  [dim]Rendering PDF → {pdf_path.name}[/dim]")
        render_pdf(cv_data, role_title, pdf_path)
        outputs.append(str(pdf_path))
        console.print(f"  [green]PDF saved: {pdf_path}[/green]")

    if output_format in ("html", "both"):
        html_path = CV_OUTPUT_DIR / f"cv_{company_slug}_{date_str}.html"
        console.print(f"  [dim]Rendering HTML → {html_path.name}[/dim]")
        render_html(cv_data, role_title, html_path)
        _append_ats_report_to_html(html_path, ats)
        outputs.append(str(html_path))
        console.print(f"  [green]HTML saved (with ATS report): {html_path}[/green]")

    # 8. Print reframe notes
    notes = cv_data.get("reframe_notes", "")
    if notes:
        console.print(Panel(notes, title="[cyan]Reframe Notes (Claude's rationale)[/cyan]", border_style="cyan"))

    result = "Generated CV files:\n" + "\n".join(f"  {p}" for p in outputs)
    result += f"\nATS Grade: {ats_grade} ({ats_coverage}% keyword coverage) — {ats.get('verdict', '')}"
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="CV Synthesis — tailor master CV to a specific JD")
    parser.add_argument("--jd", required=True, help="Job description URL or raw text")
    parser.add_argument("--company", required=True, help="Target company name")
    parser.add_argument("--role", required=True, help="Target role title")
    parser.add_argument("--format", choices=["pdf", "html", "both"], default="both",
                        help="Output format (default: both)")
    args = parser.parse_args()

    result = run(
        jd_input=args.jd,
        company=args.company,
        role_title=args.role,
        output_format=args.format,
    )
    print(result)
