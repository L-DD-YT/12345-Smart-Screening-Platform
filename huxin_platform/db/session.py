from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from huxin_platform.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


engine_kwargs: dict = {
    "future": True,
    "echo": False,
    "pool_pre_ping": True,
}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Session:
    """FastAPI session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
