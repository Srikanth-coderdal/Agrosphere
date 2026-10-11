"""
SQLite database connection using SQLAlchemy.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Always use backend/agrosphere.db, whatever folder the server is started from.
_DEFAULT_DB = Path(__file__).resolve().parent / "agrosphere.db"
DATABASE_URL = os.environ.get("AGROSPHERE_DB_URL", f"sqlite:///{_DEFAULT_DB.as_posix()}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
