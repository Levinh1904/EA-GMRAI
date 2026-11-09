"""GMRAI FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text

from app.config import settings
from app.db import Base, get_engine, session
from app.models import ApiKey, User
from app.routers import api_router, limiter
from app.security.auth import hash_api_key, hash_password
from app.services.worker import worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("gmrai")


def _bootstrap(db) -> None:
    """Seed admin user and bootstrap API key (idempotent)."""
    if not db.query(User).filter(User.username == settings.admin_username).first():
        db.add(
            User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                role="admin",
            )
        )
        logger.info("Seeded admin user %r", settings.admin_username)
    if not db.query(ApiKey).filter(ApiKey.name == "env-bootstrap").first():
        db.add(
            ApiKey(
                name="env-bootstrap",
                key_hash=hash_api_key(settings.api_key),
                role="ingest",
            )
        )
        logger.info("Seeded bootstrap ingest API key")
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data").mkdir(parents=True, exist_ok=True)
    Path(settings.artifact_dir).mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
        logger.info("Tables ensured (auto_create_tables=true)")
    if settings.auto_migrate:
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        logger.info("Alembic upgrade head applied")
    with session() as db:
        _bootstrap(db)
    worker.start_scheduler()
    yield
    worker.stop()


app = FastAPI(
    title="GMRAI — Gold Market Regime AI Intelligence",
    version="0.1.0",
    description="AI regime analysis platform for XAUUSD. Research only — no order execution.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
def health_root():
    return {"status": "ok"}


@app.get("/api/v1/health", tags=["health"])
def health():
    checks = {"api": "ok"}
    try:
        with session() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
    checks["worker"] = "running" if not worker._stop.is_set() else "stopped"
    return checks
