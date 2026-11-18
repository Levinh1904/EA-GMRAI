"""Rule-based market context (ref_v1) — explicitly NOT a model."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.ml.reference_engine import ReferenceConfig, classify_reference
from app.models import User
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import ensure_utc

reference_router = APIRouter(prefix="/reference", tags=["reference"])


def _load_context(db: Session, source: str | None = None):
    eff = active_source(db, "XAUUSD", "M15", source)
    if eff is None:
        return None, None, None
    df_m5, df_m15, df_h1 = load_candles(
        db, "XAUUSD", m5_limit=20_000, m15_limit=20_000, h1_limit=8_000, source=eff
    )
    cfg = ReferenceConfig()
    ref = classify_reference(df_m15, cfg)
    return ref, df_m15, cfg


@reference_router.get("/latest")
def reference_latest(
    source: str | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref, df, cfg = _load_context(db, source)
    if ref is None or len(ref) == 0:
        return {"status": "no_data", "note": "No closed M15 candles."}
    row = ref.iloc[-1]
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "reference_version": cfg.version,
        "ts": ensure_utc(ref.index[-1]).isoformat(),
        "regime": str(row["regime"]),
        "reason": str(row["reason"]),
        "adx_norm": round(float(row["adx_norm"]), 6) if row["adx_norm"] == row["adx_norm"] else None,
        "atr_ratio": round(float(row["atr_ratio"]), 6) if row["atr_ratio"] == row["atr_ratio"] else None,
        "displacement": round(float(row["displacement"]), 6) if row["displacement"] == row["displacement"] else None,
        "note": "Rule-based context ref_v1. Not the trade_ens model and not an order instruction.",
    }


@reference_router.get("/history")
def reference_history(
    limit: int = Query(1000, ge=1, le=5000),
    source: str | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref, df, cfg = _load_context(db, source)
    if ref is None or len(ref) == 0:
        return {"reference_version": cfg.version if cfg else None, "rows": [], "total": 0}
    tail = ref.tail(limit)
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "reference_version": cfg.version,
        "total": int(len(ref)),
        "rows": [
            {
                "ts": ensure_utc(ts).isoformat(),
                "regime": str(row["regime"]),
                "reason": str(row["reason"]),
                "adx_norm": None if row["adx_norm"] != row["adx_norm"] else round(float(row["adx_norm"]), 6),
                "atr_ratio": None if row["atr_ratio"] != row["atr_ratio"] else round(float(row["atr_ratio"]), 6),
                "displacement": None if row["displacement"] != row["displacement"] else round(float(row["displacement"]), 6),
            }
            for ts, row in tail.iterrows()
        ],
        "note": "Rule-based context ref_v1, not a model signal.",
    }


__all__ = ["reference_router"]
