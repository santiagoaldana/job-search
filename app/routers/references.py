"""References router — track who can vouch for Santiago at target companies."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.database import get_session
from app.models import Reference

router = APIRouter()


class ReferenceCreate(BaseModel):
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_name: str
    contact_title: Optional[str] = None
    relationship: Optional[str] = None
    strength: str = "medium"
    role_types: Optional[str] = None
    notes: Optional[str] = None


class ReferenceUpdate(BaseModel):
    strength: Optional[str] = None
    relationship: Optional[str] = None
    role_types: Optional[str] = None
    notes: Optional[str] = None
    contact_title: Optional[str] = None


@router.get("")
def list_references(
    company_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    q = select(Reference)
    if company_id:
        q = q.where(Reference.company_id == company_id)
    return session.exec(q.order_by(Reference.created_at.desc())).all()


@router.get("/for-company/{company_id}")
def references_for_company(company_id: int, session: Session = Depends(get_session)):
    refs = session.exec(
        select(Reference).where(Reference.company_id == company_id)
    ).all()
    return refs


@router.post("")
def add_reference(data: ReferenceCreate, session: Session = Depends(get_session)):
    valid = {"strong", "medium", "weak"}
    if data.strength not in valid:
        raise HTTPException(status_code=400, detail="strength must be strong|medium|weak")
    ref = Reference(**data.dict())
    session.add(ref)
    session.commit()
    session.refresh(ref)
    return ref


@router.patch("/{ref_id}")
def update_reference(ref_id: int, data: ReferenceUpdate, session: Session = Depends(get_session)):
    ref = session.get(Reference, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    for field, value in data.dict(exclude_none=True).items():
        setattr(ref, field, value)
    session.add(ref)
    session.commit()
    session.refresh(ref)
    return ref


@router.delete("/{ref_id}")
def delete_reference(ref_id: int, session: Session = Depends(get_session)):
    ref = session.get(Reference, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    session.delete(ref)
    session.commit()
    return {"deleted": ref_id}
