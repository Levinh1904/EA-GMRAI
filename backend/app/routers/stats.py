from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import SystemLog, User
from app.services.stats import dashboard_stats
from app.timeutil import ensure_utc

stats_router = APIRouter(prefix="/stats", tags=["stats"])


@stats_router.get("/dashboard")
def stats(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_stats(db)


system_router = APIRouter(prefix="/system", tags=["system"])


@system_router.get("/status")
def system_status(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import BackgroundJob, MarketCandle, ModelVersion

    candles_total = db.query(MarketCandle).count()
    active_models = (
        db.query(ModelVersion)
        .filter(
            ModelVersion.status == "approved",
            ModelVersion.model_type == "trade_ens",
        )
        .order_by(ModelVersion.id.desc())
        .limit(10)
        .all()
    )
    recent_jobs = db.query(BackgroundJob).order_by(BackgroundJob.id.desc()).limit(10).all()
    return {
        "candles_total": candles_total,
        "active_models": [
            {"id": m.id, "model_type": m.model_type, "model_id": m.model_id} for m in active_models
        ],
        "recent_jobs": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "error": j.error,
                "finished_at": ensure_utc(j.finished_at).isoformat() if j.finished_at else None,
            }
            for j in recent_jobs
        ],
    }


@system_router.get("/logs")
def system_logs(
    limit: int = Query(100, ge=1, le=1000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(SystemLog).order_by(SystemLog.id.desc()).limit(limit).all()
    return {
        "logs": [
            {
                "id": r.id,
                "level": r.level,
                "component": r.component,
                "message": r.message,
                "created_at": ensure_utc(r.created_at).isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
