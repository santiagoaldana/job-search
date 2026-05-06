"""Database engine and session factory."""

import os
from pathlib import Path
from sqlmodel import create_engine, Session, SQLModel

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Render provides postgres:// but SQLAlchemy needs postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, echo=False)
else:
    BASE_DIR = Path(__file__).parent.parent
    DB_PATH = BASE_DIR / "jobsearch.db"
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


def get_session():
    with Session(engine) as session:
        yield session


def create_tables():
    SQLModel.metadata.create_all(engine)


def run_migrations():
    """Add new columns to existing tables if they don't exist yet."""
    is_postgres = DATABASE_URL is not None

    migrations = [
        ("outreachrecord", "follow_up_3_sent", "BOOLEAN DEFAULT FALSE"),
        ("outreachrecord", "follow_up_7_sent", "BOOLEAN DEFAULT FALSE"),
        ("contact", "met_via", "TEXT"),
        ("contact", "relationship_notes", "TEXT"),
        ("contact", "met_at_event_id", "INTEGER"),
        ("contact", "introduced_by_contact_id", "INTEGER"),
        ("company", "is_archived", "BOOLEAN DEFAULT FALSE"),
        ("company", "ashby_slug", "TEXT"),
        ("company", "wttj_slug", "TEXT"),
        ("company", "crunchbase_url", "TEXT"),
        ("company", "apollo_enriched_at", "TEXT"),
        ("contact", "email_guessed", "BOOLEAN DEFAULT FALSE"),
        ("contact", "email_invalid", "BOOLEAN DEFAULT FALSE"),
        ("contact", "email_patterns_tried", "TEXT"),
        ("contact", "connection_request_variant", "TEXT"),
        ("lead", "salary_min", "INTEGER"),
        ("lead", "salary_max", "INTEGER"),
        ("lead", "salary_currency", "TEXT DEFAULT 'USD'"),
        ("lead", "salary_notes", "TEXT"),
        ("contentdraft", "content_type", "TEXT DEFAULT 'linkedin'"),
        ("company", "network_path_json", "TEXT"),
        ("outreachrecord", "linkedin_accepted", "BOOLEAN"),
        ("contact", "referral_target_company_id", "INTEGER"),
        ("lead", "discard_reason", "TEXT"),
        ("outreachrecord", "updated_at", "TEXT"),
        ("contact", "connected_on", "TEXT"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                if is_postgres:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                        )
                    )
                else:
                    # SQLite doesn't support IF NOT EXISTS on ALTER TABLE
                    # so we check the column list first
                    result = conn.execute(
                        __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
                    )
                    existing = [row[1] for row in result]
                    if column not in existing:
                        conn.execute(
                            __import__("sqlalchemy").text(
                                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                            )
                        )
            except Exception:
                pass  # column already exists or table doesn't exist yet

        # Fix sequence drift — reset all primary key sequences to current max
        if is_postgres:
            for table in ("contact", "company", "outreachrecord", "event", "contentdraft", "lead", "application", "interview", "offer", "reference", "aitargetsuggestion", "contentfeed", "gmailsyncstate", "strategyconfig"):
                try:
                    conn.execute(__import__("sqlalchemy").text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}"
                    ))
                except Exception:
                    pass

        conn.commit()
