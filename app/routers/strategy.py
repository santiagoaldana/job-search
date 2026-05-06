"""Strategy config endpoints — manage priority company list for Daily Brief sorting."""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Company, StrategyConfig

router = APIRouter()


def _get_or_create_config(session: Session) -> StrategyConfig:
    config = session.get(StrategyConfig, 1)
    if not config:
        config = StrategyConfig(id=1, priority_company_ids="[]")
        session.add(config)
        session.commit()
        session.refresh(config)
    return config


class StrategyUpdateRequest(BaseModel):
    promote: List[str] = []
    demote: List[str] = []


@router.get("")
def get_strategy(session: Session = Depends(get_session)):
    """Return current priority company list with names."""
    config = _get_or_create_config(session)
    ids = json.loads(config.priority_company_ids or "[]")
    companies = []
    for cid in ids:
        c = session.get(Company, cid)
        if c:
            companies.append({"id": c.id, "name": c.name, "stage": c.stage})
    return {"priority_companies": companies, "updated_at": config.updated_at}


@router.post("/update")
def update_strategy(body: StrategyUpdateRequest, session: Session = Depends(get_session)):
    """Add or remove companies from the priority list by name."""
    config = _get_or_create_config(session)
    ids: list = json.loads(config.priority_company_ids or "[]")

    promoted, demoted, not_found = [], [], []

    def _find_company(name: str) -> Optional[Company]:
        # Exact match first, then starts-with, then contains — avoids "Brex" matching "Umbrex"
        exact = session.exec(select(Company).where(Company.name.ilike(name))).first()
        if exact:
            return exact
        starts = session.exec(select(Company).where(Company.name.ilike(f"{name}%"))).first()
        if starts:
            return starts
        return session.exec(select(Company).where(Company.name.ilike(f"%{name}%"))).first()

    for name in body.promote:
        company = _find_company(name)
        if not company:
            not_found.append(name)
            continue
        if company.id not in ids:
            ids.append(company.id)
            promoted.append(company.name)

    for name in body.demote:
        company = _find_company(name)
        if company and company.id in ids:
            ids.remove(company.id)
            demoted.append(company.name)
        elif not company:
            not_found.append(name)

    config.priority_company_ids = json.dumps(ids)
    config.updated_at = datetime.utcnow().isoformat()
    session.add(config)
    session.commit()

    return {
        "promoted": promoted,
        "demoted": demoted,
        "not_found": not_found,
        "priority_count": len(ids),
    }


@router.post("/set")
def set_strategy_by_ids(company_ids: List[int], session: Session = Depends(get_session)):
    """Directly set the priority list by company IDs — bypasses name matching."""
    config = _get_or_create_config(session)
    config.priority_company_ids = json.dumps(company_ids)
    config.updated_at = datetime.utcnow().isoformat()
    session.add(config)
    session.commit()
    companies = [{"id": cid, "name": (session.get(Company, cid) or Company(name="?")).name} for cid in company_ids]
    return {"set": companies, "count": len(company_ids)}


@router.post("/seed")
def seed_priority_companies(session: Session = Depends(get_session)):
    """Seed the 4 default priority companies if the list is currently empty."""
    config = _get_or_create_config(session)
    ids: list = json.loads(config.priority_company_ids or "[]")
    if ids:
        return {"message": "already seeded", "count": len(ids)}

    priority_names = ["Sardine", "Synctera", "Flywire", "Brex"]
    seeded = []
    for name in priority_names:
        exact = session.exec(select(Company).where(Company.name.ilike(name))).first()
        c = exact or session.exec(select(Company).where(Company.name.ilike(f"{name}%"))).first()
        if c and c.id not in ids:
            ids.append(c.id)
            seeded.append(c.name)

    config.priority_company_ids = json.dumps(ids)
    config.updated_at = datetime.utcnow().isoformat()
    session.add(config)
    session.commit()
    return {"seeded": seeded, "total": len(ids)}
