from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.rate_limit import HEAVY_JOB_LIMIT, limiter
from app.deps import get_current_user, require_admin
from app.models import BacktestRun, User
from app.schemas import BacktestConfigIn
from app.services.worker import worker
from app.timeutil import ensure_utc

backtest_router = APIRouter(prefix="/backtests", tags=["backtest"])


@backtest_router.get("")
def list_runs(
    limit: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(BacktestRun).order_by(BacktestRun.id.desc()).limit(limit).all()
    return {
        "runs": [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "config": r.config_json,
                "metrics": r.metrics_json,
                "error": r.error,
                "started_at": ensure_utc(r.started_at).isoformat() if r.started_at else None,
                "finished_at": ensure_utc(r.finished_at).isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
    }


@backtest_router.post("")
@limiter.limit(HEAVY_JOB_LIMIT)
def start_backtest(
    request: Request,
    body: BacktestConfigIn,
    _: User = Depends(require_admin),
):
    job_id = worker.submit_backtest(body.model_dump())
    return {"status": "scheduled", "job_id": job_id}


@backtest_router.get("/{run_id}")
def get_run(
    run_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(BacktestRun, run_id)
    if r is None:
        raise HTTPException(404, "Không tìm thấy run.")
    return {
        "id": r.id,
        "name": r.name,
        "status": r.status,
        "config": r.config_json,
        "metrics": r.metrics_json,
        "error": r.error,
        "started_at": ensure_utc(r.started_at).isoformat() if r.started_at else None,
        "finished_at": ensure_utc(r.finished_at).isoformat() if r.finished_at else None,
    }
