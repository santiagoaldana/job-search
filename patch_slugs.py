#!/usr/bin/env python3
"""
Batch-patch job board slugs for companies in the database.
Connects directly to PostgreSQL to set greenhouse_slug, lever_slug, or ashby_slug.
"""

import os
from dotenv import load_dotenv
from sqlmodel import Session, create_engine, select
from app.models import Company

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env")
    exit(1)

# Mapping of company names to their job board slugs
COMPANY_SLUGS = {
    # Core companies researched on Friday
    "Sardine": {"ashby_slug": "sardine"},
    "Alloy": {"greenhouse_slug": "alloy"},
    "Socure": {"ashby_slug": "socure"},
    "Finix": {"lever_slug": "finix"},
    "Synctera": {"greenhouse_slug": "synctera"},
    "Marqeta": {"greenhouse_slug": "marqeta"},

    # Payments infrastructure
    "Airwallex": {"lever_slug": "airwallex"},
    "Rainforest": {"lever_slug": "rainforest"},
    "Lightspark": {"lever_slug": "lightspark"},
    "Klarna": {"greenhouse_slug": "klarna"},
    "Wise": {"greenhouse_slug": "wise"},
    "Adyen": {"greenhouse_slug": "adyen"},
    "Checkout.com": {"lever_slug": "checkout"},
    "Revolut": {"greenhouse_slug": "revolut"},
    "Mollie": {"greenhouse_slug": "mollie"},
    "Plaid": {"greenhouse_slug": "plaid"},
    "Brex": {"greenhouse_slug": "brex"},
    "Affirm": {"greenhouse_slug": "affirm"},
    "Remitly": {"greenhouse_slug": "remitly"},
    "Ripple": {"lever_slug": "ripple"},

    # Digital identity / KYC
    "Trulioo": {"lever_slug": "trulioo"},
    "Prove": {"lever_slug": "prove"},
    "Sumsub": {"ashby_slug": "sumsub"},
    "Veriff": {"greenhouse_slug": "veriff"},
    "Jumio": {"greenhouse_slug": "jumio"},
    "Onfido": {"greenhouse_slug": "onfido"},
    "Shufti Pro": {"lever_slug": "shufti"},
    "Didit": {"lever_slug": "didit"},

    # Fraud prevention
    "Riskified": {"greenhouse_slug": "riskified"},
    "Sift": {"greenhouse_slug": "sift"},
    "Feedzai": {"greenhouse_slug": "feedzai"},
    "Kount": {"lever_slug": "kount"},
    "Forter": {"greenhouse_slug": "forter"},

    # LATAM
    "Nubank": {"greenhouse_slug": "nubank"},
    "Mercado Pago": {"greenhouse_slug": "mercadopago"},
    "Banco Inter": {"greenhouse_slug": "bancointer"},
    "Albo": {"lever_slug": "albo"},
    "Klar": {"lever_slug": "klar"},
    "Rappi": {"greenhouse_slug": "rappi"},
    "Uala": {"greenhouse_slug": "uala"},
    "Clip": {"greenhouse_slug": "clip"},
    "Stone": {"greenhouse_slug": "stone"},

    # Infrastructure / supporting
    "Figure Technologies": {"greenhouse_slug": "figure"},
    "Bolt": {"greenhouse_slug": "bolt"},
    "Yapstone": {"greenhouse_slug": "yapstone"},
    "Bandwidth": {"greenhouse_slug": "bandwidth"},
    "Spreedly": {"lever_slug": "spreedly"},
    "Shift4 Payments": {"greenhouse_slug": "shift4"},
    "Yapak": {"lever_slug": "yapak"},
    "M-Pesa": {"greenhouse_slug": "safaricom"},
    "OKX": {"greenhouse_slug": "okx"},
    "Bancor": {"greenhouse_slug": "bancor"},
    "Compound": {"greenhouse_slug": "compound"},
    "Aave": {"greenhouse_slug": "aave"},
    "Deel": {"greenhouse_slug": "deel"},
    "Melio": {"greenhouse_slug": "melio"},
    "Ramp": {"greenhouse_slug": "ramp"},
    "Circle": {"greenhouse_slug": "circle"},
    "Maven": {"lever_slug": "maven"},
    "Flywire": {"greenhouse_slug": "flywire"},
    "Chime": {"greenhouse_slug": "chime"},
    "Sift": {"greenhouse_slug": "sift"},
}

engine = create_engine(DATABASE_URL, echo=False)

with Session(engine) as session:
    updated = 0
    not_found = 0

    for company_name, slug_data in COMPANY_SLUGS.items():
        stmt = select(Company).where(Company.name == company_name)
        company = session.exec(stmt).first()

        if not company:
            print(f"⚠️  {company_name}: not found in database")
            not_found += 1
            continue

        # Update the appropriate slug field
        for slug_field, slug_value in slug_data.items():
            setattr(company, slug_field, slug_value)

        session.add(company)
        updated += 1

        slug_str = ", ".join(f"{k}={v}" for k, v in slug_data.items())
        print(f"✅ {company_name} (id {company.id}): {slug_str}")

    session.commit()

    print(f"\n📊 Updated: {updated}, Not found: {not_found}")
    print(f"💾 Committed to database")
