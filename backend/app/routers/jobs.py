"""Background-job lookup.

`POST /training/run`, `/backtests`, `/history/run` all return a `job_id`, but
nothing could resolve it — the handle was unusable. These routes close that gap
so a client can poll one id instead of guessing which table to query.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import BackgroundJob, User
from app.services.worker import worker
from app.timeutil import ensure_utc

jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])


def _payload(j: BackgroundJob) -> dict:
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status,
        "params": j.params_json,
        "result": j.result_json,
        "error": j.error,
        "created_at": ensure_utc(j.created_at).isoformat() if j.created_at else None,
        "started_at": ensure_utc(j.started_at).isoformat() if j.started_at else None,
        "finished_at": ensure_utc(j.finished_at).isoformat() if j.finished_at else None,
        "duration_seconds": (
            round((ensure_utc(j.finished_at) - ensure_utc(j.started_at)).total_seconds(), 1)
            if j.finished_at and j.started_at
            else None
        ),
    }


@jobs_router.get("")
def list_jobs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, pattern="^(pending|running|done|failed)$"),
    job_type: str | None = Query(None, max_length=32),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(BackgroundJob)
    if status:
        q = q.filter(BackgroundJob.status == status)
    if job_type:
        q = q.filter(BackgroundJob.job_type == job_type)
    total = q.count()
    rows = q.order_by(BackgroundJob.id.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": [_payload(j) for j in rows],
        # In-process pool: restarting the API loses queued work. Reported so the
        # UI can warn instead of silently showing "running" forever.
        "executor": {
            "max_workers": worker.max_workers,
            "running": worker.executor is not None
            and not getattr(worker.executor, "_shutdown", False),
            "durable": False,
        },
    }


@jobs_router.get("/{job_id}")
def get_job(
    job_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job.")
    return _payload(job)


@jobs_router.post("/{job_id}/cancel")
def cancel_job(
    job_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mark a stuck job failed.

    The in-process thread pool cannot interrupt a running job, so this only
    releases the *record* — which is what blocks the UI and the retrain check.
    """
    job = db.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job.")
    if job.status in ("done", "failed"):
        raise HTTPException(400, f"Job đã kết thúc (status={job.status}).")
    job.status = "failed"
    job.error = "cancelled by admin"
    from app.timeutil import utcnow

    job.finished_at = utcnow()
    db.commit()
    return {"status": "failed", "id": job.id, "note": "Job được đánh dấu huỷ."}
