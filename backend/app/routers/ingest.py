from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, ingest_identity
from app.models import DataSyncLog, User
from app.schemas import CandleBatchIn
from app.rate_limit import INGEST_LIMIT, limiter
from app.services.ingestion import IngestionError, ingest_candles

ingest_router = APIRouter(prefix="/ingest", tags=["ingestion"])


@ingest_router.post("/candles")
@limiter.limit(INGEST_LIMIT)
def ingest(
    request: Request,
    body: CandleBatchIn,
    timeframe: str = Query("M15", pattern="^(M5|M15|H1)$"),
    identity: dict = Depends(ingest_identity),
    db: Session = Depends(get_db),
):
    """Collector endpoint: upsert closed candles (X-API-Key auth)."""
    try:
        summary = ingest_candles(
            db,
            [c.model_dump() for c in body.candles],
            timeframe,
            collector_id=identity["collector_id"],
        )
    except IngestionError as e:
        raise HTTPException(422, str(e))
    return {"status": "ok", "collector_id": identity["collector_id"], **summary}


@ingest_router.get("/status")
def status_(
    limit: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = db.query(DataSyncLog).order_by(DataSyncLog.id.desc()).limit(limit).all()
    return {
        "recent_syncs": [
            {
                "id": s.id,
                "collector_id": s.collector_id,
                "timeframe": s.timeframe,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "status": s.status,
                "received": s.candles_received,
                "inserted": s.candles_inserted,
                "updated": s.candles_updated,
                "message": s.message,
            }
            for s in logs
        ]
    }
