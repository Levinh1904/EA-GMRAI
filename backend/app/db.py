"""Database engine/session management."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None


def _make_engine(url: str, pool_class=None):
    kwargs: dict = {"pool_pre_ping": True}
    if pool_class is not None:
        kwargs["poolclass"] = pool_class
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return create_engine(url, **kwargs)


def init_engine(url: str | None = None, pool_class=None):
    global _engine, _session_factory
    _engine = _make_engine(url or settings.database_url, pool_class)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def session():
    """Return a fresh Session. Stable accessor — callers must not bind the
    factory name at import time (it is (re)bound by init_engine)."""
    global _session_factory
    if _session_factory is None:
        init_engine()
    return _session_factory()


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        init_engine()
    return _engine


def get_db():
    db = session()
    try:
        yield db
    finally:
        db.close()


def reset_engine():
    """Test helper: drop the current engine binding."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


# Backwards-compatible alias for code/tests that import the name directly.
SessionLocal = None  # type: ignore[assignment]  # deprecated: use session()
