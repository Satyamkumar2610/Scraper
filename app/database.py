"""
database.py — SQLAlchemy engine, session factory, and helpers.

Uses connection pooling (pool_size=20, overflow=10) for high-throughput
batch inserts.  `init_db()` creates all ORM-mapped tables.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Yield a transactional database session that auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table defined on Base.metadata (if not exists)."""
    Base.metadata.create_all(bind=engine)
