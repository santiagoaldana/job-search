"""
One-time migration: existing JSON/CSV data → SQLite via SQLModel.
Preserves all LAMP scores, leads, outreach records, events, and contacts.

Run: python3 -m app.migrate
"""

import csv
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict

# Load .env before any imports that need API keys
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from sqlmodel import Session, SQLModel, create_engine, select

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "jobsearch.db"

from app.models import (
    Company, Contact, Lead, OutreachRecord,
    Event, ContentDraft, AITargetSuggestion
)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def create_tables():
    SQLModel.metadata.create_all(engine)
    print("✓ Tables created")


def _parse_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return None


def migrate_lamp(session: Session) -> Dict[str, int]:
    """Migrate lamp_list.json → Company table. Returns name→id map."""
    lamp_path = DATA_DIR / "lamp_list.json"
    if not lamp_path.exists():
        print("  ✗ lamp_list.json not found — skipping")
        return {}

    lamp_data = json.loads(lamp_path.read_text())
    name_to_id: Dict[str, int] = {}
    created = 0

    for entry in lamp_data:
        name = entry.get("company", "").strip()
        if not name:
            continue

        # Check for existing (idempotent re-runs)
        existing = session.exec(select(Company).where(Company.name == name)).first()
        if existing:
            name_to_id[name] = existing.id
            continue

        motivation = int(entry.get("motivation", 5))
        is_archived = motivation < 7  # hide low-motivation from active funnel

        company = Company(
            name=name,
            motivation=motivation,
            advocacy_score=float(entry.get("advocacy_score", 1.0)),
            postings_score=float(entry.get("postings_score", 1.0)),
            lamp_score=float(entry.get("lamp_score", 5.0)),
            stage="pool",
            is_archived=is_archived,
            suggested_by_ai=False,
        )
        session.add(company)
        session.flush()  # get id
        name_to_id[name] = company.id
        created += 1

    session.commit()
    print(f"✓ Companies migrated: {created} created ({len(lamp_data)} total in LAMP)")
    return name_to_id


def migrate_contacts(session: Session, name_to_id: Dict[str, int]) -> None:
    """Migrate contacts_export.csv → Contact table, linked to companies."""
    csv_path = BASE_DIR / "cv" / "contacts_export.csv"
    if not csv_path.exists():
        print("  ✗ contacts_export.csv not found — skipping")
        return

    created = 0
    import io as _io
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        lines = f.readlines()
    # LinkedIn exports have preamble lines before the real CSV header
    header_idx = next(
        (i for i, l in enumerate(lines) if l.startswith("First Name,")), 0
    )
    reader = csv.DictReader(_io.StringIO("".join(lines[header_idx:])))

    for row in reader:
        first = row.get("First Name", "").strip()
        last = row.get("Last Name", "").strip()
        name = f"{first} {last}".strip()
        company_name = row.get("Company", "").strip()
        if not name or not company_name:
            continue

        company_id = name_to_id.get(company_name)
        if not company_id:
            for k, v in name_to_id.items():
                if k.lower() == company_name.lower():
                    company_id = v
                    break

        contact = Contact(
            company_id=company_id,
            name=name,
            title=row.get("Position", "").strip() or None,
            linkedin_url=row.get("URL", "").strip() or None,
            email=row.get("Email Address", "").strip() or None,
            connection_degree=1,
            warmth="warm" if company_id else "cold",
            connected_on=row.get("Connected On", "").strip() or None,
        )
        session.add(contact)
        created += 1

        if created % 500 == 0:
            session.flush()
            print(f"  … {created} contacts processed")

    session.commit()
    print(f"✓ Contacts migrated: {created}")


def migrate_leads(session: Session, name_to_id: Dict[str, int]) -> None:
    """Migrate leads_pipeline.json → Lead table."""
    leads_path = DATA_DIR / "leads_pipeline.json"
    if not leads_path.exists():
        print("  ✗ leads_pipeline.json not found — skipping")
        return

    leads_data = json.loads(leads_path.read_text())
    created = 0
    ACCEPTED_LOCATIONS = {
        "cambridge", "boston", "remote", "hybrid", "nationwide",
        "us remote", "greater boston", "ma", "massachusetts"
    }

    for entry in leads_data:
        company_name = entry.get("company", "").strip()
        company_id = name_to_id.get(company_name)
        if not company_id:
            for k, v in name_to_id.items():
                if k.lower() == company_name.lower():
                    company_id = v
                    break

        location_raw = (entry.get("location") or "").lower()
        location_compatible = any(loc in location_raw for loc in ACCEPTED_LOCATIONS)
        if not location_raw:
            location_compatible = True  # unknown = assume compatible

        lead = Lead(
            company_id=company_id,
            title=entry.get("title", "").strip(),
            url=entry.get("url") or None,
            location=entry.get("location") or None,
            description=entry.get("description_snippet") or None,
            fit_score=None,  # will be scored on next refresh
            location_compatible=location_compatible,
            status="active",
            source=entry.get("source", "career_page"),
            posted_date=_parse_date(entry.get("posted_date")),
        )
        session.add(lead)
        created += 1

    session.commit()
    print(f"✓ Leads migrated: {created}")


def migrate_outreach(session: Session, name_to_id: Dict[str, int]) -> None:
    """Migrate outreach_tracker.json → OutreachRecord table."""
    outreach_path = DATA_DIR / "outreach_tracker.json"
    if not outreach_path.exists():
        print("  ✗ outreach_tracker.json not found — skipping")
        return

    records = json.loads(outreach_path.read_text())
    created = 0

    for entry in records:
        company_name = entry.get("company", "").strip()
        company_id = name_to_id.get(company_name)

        sent_date = _parse_date(entry.get("sent_date"))
        follow_up_due = _parse_date(entry.get("follow_up_due"))
        second_due = _parse_date(entry.get("second_contact_due"))

        record = OutreachRecord(
            company_id=company_id,
            channel=entry.get("channel", "email"),
            sent_at=sent_date,
            body=entry.get("generated_email") or None,
            subject=entry.get("generated_subject") or None,
            response_status="positive" if entry.get("status") == "responded" else "pending",
            follow_up_3_due=follow_up_due,
            follow_up_7_due=second_due,
            notes=entry.get("notes") or None,
        )
        session.add(record)
        created += 1

    session.commit()
    print(f"✓ Outreach records migrated: {created}")


def migrate_events(session: Session) -> None:
    """Migrate events_cache.json → Event table."""
    events_path = DATA_DIR / "events_cache.json"
    if not events_path.exists():
        print("  ✗ events_cache.json not found — skipping")
        return

    events_data = json.loads(events_path.read_text())
    if isinstance(events_data, dict):
        events_list = events_data.get("events", list(events_data.values()))
    else:
        events_list = events_data

    created = 0
    for entry in events_list:
        event = Event(
            name=entry.get("name", "Unknown Event"),
            date=_parse_date(entry.get("date")),
            location=entry.get("location") or None,
            url=entry.get("url") or None,
            cost=entry.get("cost") or None,
            description=entry.get("description") or entry.get("summary") or None,
            category=entry.get("category", "strategic").lower().replace(" ", "_"),
            utility=float(entry.get("utility", 5)),
            risk=float(entry.get("risk", 5)),
            net_score=float(entry.get("net_score", 3)),
            action_prompt=entry.get("action_prompt") or None,
        )
        session.add(event)
        created += 1

    session.commit()
    print(f"✓ Events migrated: {created}")


def migrate_content(session: Session) -> None:
    """Migrate content_cache.json drafts → ContentDraft table."""
    cache_path = DATA_DIR / "content_cache.json"
    drafts_path = DATA_DIR / "content_drafts.md"

    if not cache_path.exists():
        print("  ✗ content_cache.json not found — skipping")
        return

    cache = json.loads(cache_path.read_text())
    drafts = cache.get("drafts", []) if isinstance(cache, dict) else []
    created = 0

    for draft in drafts:
        body = draft.get("post_text") or draft.get("body") or draft.get("draft") or ""
        if not body:
            continue
        cd = ContentDraft(
            source_url=draft.get("article_url") or draft.get("url") or None,
            source_title=draft.get("article_title") or draft.get("title") or None,
            body=body,
            net_score=float(draft.get("net_score", 0)),
            controversy_score=float(draft.get("controversy_score", 0)),
            risk_score=float(draft.get("risk_score", 0)),
            status="pending",
        )
        session.add(cd)
        created += 1

    session.commit()
    print(f"✓ Content drafts migrated: {created}")


def report(session: Session) -> None:
    from sqlmodel import func
    counts = {
        "Companies": session.exec(select(Company)).all().__len__(),
        "Contacts": session.exec(select(Contact)).all().__len__(),
        "Leads": session.exec(select(Lead)).all().__len__(),
        "Outreach records": session.exec(select(OutreachRecord)).all().__len__(),
        "Events": session.exec(select(Event)).all().__len__(),
        "Content drafts": session.exec(select(ContentDraft)).all().__len__(),
    }
    active = session.exec(select(Company).where(Company.is_archived == False)).all().__len__()
    print("\n── Migration Summary ──────────────────────────")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  Active companies (motivation ≥ 7): {active}")
    print(f"\n  Database: {DB_PATH}")
    print("───────────────────────────────────────────────")


def main():
    print("Job Search System v2 — Data Migration")
    print("=" * 45)
    create_tables()

    with Session(engine) as session:
        print("\nMigrating LAMP companies…")
        name_to_id = migrate_lamp(session)

        print("\nMigrating contacts…")
        migrate_contacts(session, name_to_id)

        print("\nMigrating leads…")
        migrate_leads(session, name_to_id)

        print("\nMigrating outreach records…")
        migrate_outreach(session, name_to_id)

        print("\nMigrating events…")
        migrate_events(session)

        print("\nMigrating content drafts…")
        migrate_content(session)

        report(session)

    print("\n✓ Migration complete.")


if __name__ == "__main__":
    main()
