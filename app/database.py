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
