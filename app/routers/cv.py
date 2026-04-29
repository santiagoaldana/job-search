"""CV router — chat-driven edits, multi-format export, version management."""

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()


class CVChatRequest(BaseModel):
    instruction: str                    # natural language edit instruction
    lead_id: Optional[int] = None       # if set, tailor to this lead's JD
    version_name: Optional[str] = None  # name for the saved version


class CVExportRequest(BaseModel):
    version_name: Optional[str] = None  # None = master
    format: str = "pdf"                 # pdf | html | plaintext


@router.get("/master")
def get_master_cv():
    """Return the canonical master CV JSON."""
    from app.services.cv_manager import load_master_cv
    return load_master_cv()


@router.post("/chat")
async def chat_edit(req: CVChatRequest):
    """
    Natural language CV edit. Returns a structured diff:
    { "diff": [{section, original, proposed}], "version_name": str }
    Santiago approves or rejects each section; call /cv/approve to save.
    """
    from app.services.cv_manager import chat_edit_cv
    try:
        result = await chat_edit_cv(
            instruction=req.instruction,
            lead_id=req.lead_id,
            version_name=req.version_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ApproveDiffRequest(BaseModel):
    version_name: str
    approved_sections: list


@router.post("/approve")
async def approve_diff(req: ApproveDiffRequest):
    version_name, approved_sections = req.version_name, req.approved_sections
    """
    Approve specific sections from a pending diff and save the version.
    approved_sections: list of section names to accept (others keep original).
    """
    from app.services.cv_manager import apply_approved_diff
    try:
        path = await apply_approved_diff(req.version_name, req.approved_sections)
        return {"saved": True, "version_path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/versions")
def list_versions():
    """List all saved CV versions."""
    from app.services.cv_manager import list_cv_versions
    return list_cv_versions()


@router.get("/export")
def export_cv(
    format: str = "pdf",
    version_name: Optional[str] = None,
):
    """Export CV in the requested format. Returns file download."""
    from app.services.cv_manager import export_cv as _export
    try:
        path = _export(format=format, version_name=version_name)
        media_types = {
            "pdf": "application/pdf",
            "html": "text/html",
            "plaintext": "text/plain",
        }
        return FileResponse(
            path=str(path),
            media_type=media_types.get(format, "application/octet-stream"),
            filename=path.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SynthesizeRequest(BaseModel):
    lead_id: int
    version_name: Optional[str] = None


@router.post("/upload-master")
async def upload_master_cv(file: UploadFile = File(...)):
    """
    Accept an edited .docx or .json file and replace master_cv.json.
    For .docx: extracts text with python-docx, then uses Claude Haiku
    to convert it into the master_cv.json schema.
    """
    from app.services.cv_manager import MASTER_CV_PATH, load_master_cv
    import anthropic, re

    content = await file.read()
    fname = file.filename or ""

    if fname.endswith(".json"):
        try:
            data = json.loads(content)
        except Exception:
            raise HTTPException(400, "Invalid JSON file")

    elif fname.endswith(".docx"):
        # Extract plain text from Word doc
        try:
            import io
            from docx import Document as DocxDocument
            doc = DocxDocument(io.BytesIO(content))
            raw_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise HTTPException(400, f"Could not read .docx: {e}")

        # Use Claude Haiku to convert to master_cv.json schema
        client = anthropic.Anthropic()
        schema_example = json.dumps(load_master_cv(), indent=2)[:3000]
        prompt = f"""Convert this CV text into the exact JSON schema shown below.
Preserve all content faithfully — do not fabricate or omit anything.
Return ONLY valid JSON, no markdown fences.

SCHEMA EXAMPLE (follow this structure exactly):
{schema_example}

CV TEXT TO CONVERT:
{raw_text[:8000]}"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        try:
            data = json.loads(raw)
        except Exception:
            raise HTTPException(500, "Claude returned invalid JSON — try again or upload .json directly")

    else:
        raise HTTPException(400, "Only .docx or .json files accepted")

    # Validate required keys
    for key in ("name", "summary", "experience"):
        if key not in data:
            raise HTTPException(422, f"Missing required field: '{key}' — check the file format")

    # Back up existing master before overwriting
    backup_path = MASTER_CV_PATH.parent / "master_cv_backup.json"
    if MASTER_CV_PATH.exists():
        backup_path.write_text(MASTER_CV_PATH.read_text())

    MASTER_CV_PATH.write_text(json.dumps(data, indent=2))
    return {"ok": True, "name": data.get("name"), "experience_count": len(data.get("experience", []))}


class CoverLetterRequest(BaseModel):
    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    job_description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_linkedin_url: Optional[str] = None
    contact_notes: Optional[str] = None
    version_name: Optional[str] = None


@router.post("/cover-letter")
async def cover_letter(req: CoverLetterRequest):
    """Generate a personalized cover letter using a two-stage Haiku→Opus pipeline."""
    from app.services.cv_manager import generate_cover_letter
    try:
        return await generate_cover_letter(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ATSScoreRequest(BaseModel):
    version_name: Optional[str] = None


@router.post("/ats-score")
async def ats_score(req: ATSScoreRequest):
    """Run an ATS compatibility check on the master CV or a specific version."""
    from app.services.cv_manager import load_master_cv, load_version
    import anthropic

    try:
        cv = load_version(req.version_name) if req.version_name else load_master_cv()
    except Exception:
        cv = load_master_cv()

    client = anthropic.Anthropic()
    prompt = f"""You are an ATS (Applicant Tracking System) expert and senior recruiter.

Analyze this CV JSON for ATS compatibility and return ONLY valid JSON (no markdown fences):

{{
  "score": <integer 1-10>,
  "keyword_coverage": "<strong|moderate|weak> — <one sentence>",
  "structure_issues": ["<issue 1>"],
  "formatting_flags": ["<flag 1>"],
  "top_strengths": ["<strength 1>", "<strength 2>"],
  "quick_wins": ["<specific highest-impact fix>", "<fix 2>"],
  "verdict": "<one sentence summary>"
}}

Focus on: keyword density for fintech/payments/AI, section headers, quantified achievements, action verbs, and ATS-parseable structure.

CV JSON:
{json.dumps(cv, indent=2)[:5000]}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        import re
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/synthesize")
async def synthesize_for_lead(req: SynthesizeRequest):
    lead_id, version_name = req.lead_id, req.version_name
    """
    Generate a tailored CV version for a specific lead (fit-based reordering).
    Returns the diff for review before saving.
    """
    from app.database import engine
    from sqlmodel import Session
    from app.models import Lead, Company

    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        company = session.get(Company, lead.company_id) if lead.company_id else None

    from app.services.cv_manager import synthesize_for_lead as _synth
    try:
        result = await _synth(
            lead=lead,
            company_name=company.name if company else "Unknown",
            version_name=version_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
