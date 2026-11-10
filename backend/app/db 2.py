"""Database engine/session management."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal: sessionmaker | None = None


def _make_engine(url: str, pool_class=None):
    kwargs: dict = {"pool_pre_ping": True}
    if pool_class is not None:
        kwargs["poolclass"] = pool_class
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def init_engine(url: str | None = None, pool_class=None):
    global _engine, SessionLocal
    _engine = _make_engine(url or settings.database_url, pool_class)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        init_engine()
    return _engine


def get_db():
    global SessionLocal
    if SessionLocal is None:
        init_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_engine():
    """Test helper: drop the current engine binding."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None
