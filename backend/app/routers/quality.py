from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import DataQualityReport, User
from app.services.quality import run_quality_check
from app.services.worker import worker
from app.timeutil import ensure_utc

quality_router = APIRouter(prefix="/quality", tags=["quality"])


@quality_router.get("/reports")
def reports(
    limit: int = Query(20, ge=1, le=200),
    timeframe: str | None = Query(None, pattern="^(M5|M15|H1)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(DataQualityReport)
    if timeframe:
        q = q.filter(DataQualityReport.timeframe == timeframe)
    rows = q.order_by(DataQualityReport.id.desc()).limit(limit).all()
    return {
        "reports": [
            {
                "id": r.id,
                "timeframe": r.timeframe,
                "checked_at": ensure_utc(r.checked_at).isoformat() if r.checked_at else None,
                "total_candles": r.total_candles,
                "missing_count": r.missing_count,
                "duplicate_count": r.duplicate_count,
                "gap_count": r.gap_count,
                "bad_candle_count": r.bad_candle_count,
                "stale_ts": ensure_utc(r.stale_ts).isoformat() if r.stale_ts else None,
                "stale": bool((r.report_json or {}).get("stale")),
            }
            for r in rows
        ]
    }


@quality_router.post("/run")
def run_check(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    out = {}
    for tf in ("M5", "M15", "H1"):
        out[tf] = run_quality_check(db, symbol, tf)
    return {"status": "done", "results": out}
