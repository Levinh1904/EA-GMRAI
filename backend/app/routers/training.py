from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import TrainingRun, User
from app.schemas import TrainingConfigIn
from app.services.worker import worker
from app.timeutil import ensure_utc

training_router = APIRouter(prefix="/training", tags=["training"])


@training_router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(TrainingRun).order_by(TrainingRun.id.desc()).limit(limit).all()
    return {
        "runs": [
            {
                "id": r.id,
                "model_type": r.model_type,
                "params": r.params_json,
                "feature_version": r.feature_version,
                "status": r.status,
                "metrics": r.metrics_json,
                "error": r.error,
                "started_at": ensure_utc(r.started_at).isoformat() if r.started_at else None,
                "finished_at": ensure_utc(r.finished_at).isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
    }


@training_router.post("/run")
def start_training(
    body: TrainingConfigIn,
    _: User = Depends(require_admin),
):
    job_id = worker.submit_training(body.model_dump())
    return {"status": "scheduled", "job_id": job_id}


@training_router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(TrainingRun, run_id)
    if r is None:
        return {"error": "not found"}
    return {
        "id": r.id,
        "status": r.status,
        "params": r.params_json,
        "metrics": r.metrics_json,
        "error": r.error,
        "started_at": ensure_utc(r.started_at).isoformat() if r.started_at else None,
        "finished_at": ensure_utc(r.finished_at).isoformat() if r.finished_at else None,
    }
