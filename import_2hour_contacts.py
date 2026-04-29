"""
One-time import of contacts from "Mastering 2 hour Job Search" CSV.

Parses Contact + Intro by or when + email columns and upserts into the
Contact table, populating met_via and attempting to match funnel companies.
"""

import csv
import re
import sys
from pathlib import Path

# Load .env so DB path resolves correctly
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            import os
            os.environ.setdefault(k.strip(), v.strip())

CSV_PATH = Path(__file__).parent / "Input" / "Mastering 2 hour Job Search.csv"


def extract_email(raw: str):
    m = re.search(r"[\w.+\-]+@[\w.\-]+\.\w+", raw)
    return m.group(0).lower() if m else None


def split_name_title(raw: str):
    raw = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
    # Split on LinkedIn-style separators that follow a name
    for sep in [" - ", " | ", " @ ", ","]:
        if sep in raw:
            name_part, rest = raw.split(sep, 1)
            words = name_part.strip().split()
            if 1 <= len(words) <= 5:
                return name_part.strip(), rest.strip()[:200]
    # No separator — take first 3 words as name
    words = raw.split()
    name = " ".join(words[:3])
    title = " ".join(words[3:])[:200] if len(words) > 3 else ""
    return name, title


def match_company(company_hint: str, companies: list):
    if not company_hint:
        return None
    hint = company_hint.lower().strip()
    for company in companies:
        cname = (company.name or "").lower()
        if cname and (cname == hint or cname in hint or hint in cname):
            return company.id
    return None


def run():
    from app.database import engine
    from sqlmodel import Session, select
    from app.models import Contact, Company

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Total rows in CSV: {len(rows)}")

    with Session(engine) as session:
        all_companies = session.exec(
            select(Company).where(Company.is_archived == False)
        ).all()

        parsed = 0
        matched = 0
        upserted = 0
        skipped = 0

        for row in rows:
            raw_contact = (row.get("Contact") or "").strip()
            if not raw_contact:
                continue

            name, title_hint = split_name_title(raw_contact)
            if not name or len(name) < 2:
                continue

            raw_email = (row.get("email") or "").strip()
            email = extract_email(raw_email)
            raw_intro = (row.get("Intro by or when") or "").strip()
            met_via = raw_intro[:200] if raw_intro else None

            # Try to infer company from the contact text
            company_id = None
            # Look for company names mentioned in the raw contact text
            company_id = match_company(raw_contact, all_companies)

            parsed += 1

            # Upsert: match by email first, then by name
            existing = None
            if email:
                existing = session.exec(
                    select(Contact).where(Contact.email == email)
                ).first()
            if not existing:
                existing = session.exec(
                    select(Contact).where(Contact.name == name)
                ).first()

            if existing:
                changed = False
                # Only fill in blanks — never overwrite existing values
                if met_via and not existing.met_via:
                    existing.met_via = met_via
                    changed = True
                if email and not existing.email:
                    existing.email = email
                    changed = True
                if title_hint and not existing.title:
                    existing.title = title_hint[:200]
                    changed = True
                if company_id and not existing.company_id:
                    existing.company_id = company_id
                    changed = True
                if changed:
                    session.add(existing)
                    upserted += 1
                else:
                    skipped += 1
            else:
                # Create new contact
                contact = Contact(
                    name=name,
                    title=title_hint[:200] if title_hint else None,
                    email=email,
                    company_id=company_id,
                    connection_degree=1,
                    warmth="warm" if company_id else "cold",
                    met_via=met_via,
                )
                session.add(contact)
                upserted += 1
                if company_id:
                    matched += 1

        session.commit()

    print(f"\nResults:")
    print(f"  Parsed rows with a contact name: {parsed}")
    print(f"  Matched to a funnel company:     {matched}")
    print(f"  Contacts upserted / created:     {upserted}")
    print(f"  Already up-to-date (skipped):    {skipped}")


if __name__ == "__main__":
    run()
