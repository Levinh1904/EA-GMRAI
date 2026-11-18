"""TRADE_ENS compatibility view.

The legacy HMM/RF endpoints still exist in the codebase, but this router never
returns regime labels. `/regime` is kept as a compatibility name for the UI and
returns the current trade_ens signal (LONG / SHORT / NO_TRADE).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services.trade_signal import (
    TradeSignalError,
    compute_latest_signal,
    compute_signal_history,
)
from app.timeutil import ensure_utc, utcnow

regime_router = APIRouter(prefix="/regime", tags=["trade_ens"])


@regime_router.get("/latest")
def latest(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        sig = compute_latest_signal(db)
    except TradeSignalError as e:
        return {
            "symbol": symbol,
            "timeframe": "M15",
            "timestamp": utcnow().isoformat(),
            "regime": "TRADE_ENS",
            "engine": "trade_ens",
            "confidence": 0.0,
            "probabilities": {"trade_ens": {"LONG": 0.0, "SHORT": 0.0}},
            "model_version": None,
            "feature_version": None,
            "data_timestamp": None,
            "data_source": None,
            "expiry": None,
            "reason_codes": [e.code],
            "permission": "NO_TRADE",
            "data_age_minutes": None,
            "trade_ens": None,
            "message": str(e),
        }
    p_long = float(sig.get("p_long", 0.0))
    p_short = float(sig.get("p_short", 0.0))
    return {
        "symbol": sig.get("symbol", symbol),
        "timeframe": sig.get("timeframe", "M15"),
        "timestamp": sig.get("bar_ts"),
        "regime": "TRADE_ENS",
        "engine": "trade_ens",
        "confidence": max(p_long, p_short),
        "probabilities": {"trade_ens": {"LONG": p_long, "SHORT": p_short}},
        "model_version": sig.get("model_version_id"),
        "feature_version": sig.get("feature_version"),
        "data_timestamp": sig.get("bar_ts"),
        "data_source": sig.get("source"),
        "expiry": sig.get("expires_at"),
        "reason_codes": ["TRADE_ENS_ONLY", sig.get("signal", "NO_TRADE")],
        "permission": "NO_TRADE",
        "data_age_minutes": round(float(sig.get("data_age_seconds", 0.0)) / 60.0, 1),
        "trade_ens": sig,
        "message": "TRADE_ENS is the only model; output is LONG/SHORT/NO_TRADE.",
    }


@regime_router.get("/history")
def history(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(500, ge=1, le=5000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        hist = compute_signal_history(db, limit=limit)
    except TradeSignalError as e:
        return {"history": [], "reason_codes": [e.code], "model_version": None}
    rows = []
    for bar in hist.get("bars", []):
        p_long = float(bar.get("p_long", 0.0))
        p_short = float(bar.get("p_short", 0.0))
        raw_ts = bar.get("ts")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).isoformat()
            except ValueError:
                ts = raw_ts
        else:
            ts = ensure_utc(raw_ts).isoformat() if raw_ts else None
        rows.append(
            {
                "ts": ts,
                "regime": "TRADE_ENS",
                "signal": bar.get("signal", "NO_TRADE"),
                "confidence": max(p_long, p_short),
                "probabilities": {"trade_ens": {"LONG": p_long, "SHORT": p_short}},
                "reason_codes": ["TRADE_ENS_ONLY", bar.get("signal", "NO_TRADE")],
                "permission": "NO_TRADE",
                "model_version_id": hist.get("model_version_id"),
            }
        )
    return {
        "history": rows,
        "model_version": hist.get("model_version_id"),
        "thresholds": hist.get("thresholds"),
        "warnings": hist.get("warnings", []),
    }
