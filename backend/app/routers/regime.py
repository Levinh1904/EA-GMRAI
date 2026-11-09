from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ModelPrediction, User
from app.services.prediction import regime_latest
from app.timeutil import ensure_utc

regime_router = APIRouter(prefix="/regime", tags=["regime"])


@regime_router.get("/latest")
def latest(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current operational regime (UNKNOWN on stale data/inference failure)."""
    return regime_latest(db, symbol)


@regime_router.get("/history")
def history(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(500, ge=1, le=5000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ModelPrediction)
        .filter(ModelPrediction.symbol == symbol)
        .order_by(ModelPrediction.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "history": [
            {
                "ts": ensure_utc(r.ts).isoformat(),
                "regime": r.regime,
                "confidence": r.confidence,
                "probabilities": r.probabilities_json,
                "reason_codes": r.reason_codes_json,
                "permission": r.permission,
                "model_version_id": r.model_version_id,
            }
            for r in reversed(rows)
        ]
    }
