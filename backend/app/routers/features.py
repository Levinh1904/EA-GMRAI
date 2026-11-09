from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import MarketFeature, User
from app.timeutil import ensure_utc

features_router = APIRouter(prefix="/features", tags=["features"])


@features_router.get("")
def list_features(
    timeframe: str = Query("M15"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    feature_version: str = Query("v1"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(MarketFeature).filter(
        MarketFeature.timeframe == timeframe, MarketFeature.feature_version == feature_version
    )
    total = q.count()
    rows = q.order_by(MarketFeature.ts.asc()).offset(offset).limit(limit).all()
    cols = [
        "ret1", "ret4", "atr_ratio", "ema_slope", "efficiency_ratio", "adx_norm", "di_gap",
        "h1_ema_slope", "h1_atr_ratio", "h1_adx_norm", "h1_trend_context",
        "m5_ret_short", "m5_vol_ratio", "m5_momentum",
    ]
    return {
        "total": total,
        "feature_version": feature_version,
        "features": [
            {"ts": ensure_utc(r.ts).isoformat(), **{c: getattr(r, c) for c in cols}}
            for r in rows
        ],
    }
