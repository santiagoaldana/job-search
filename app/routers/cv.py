"""CV router — chat-driven edits, multi-format export, version management."""

from typing import Optional
from fastapi import APIRouter, HTTPException
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
