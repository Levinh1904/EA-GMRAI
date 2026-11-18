"""Telegram and forecast endpoints — trade_ens signals only."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import User
from app.services import telegram as tg
from app.services.trade_signal import (
    TradeSignalError,
    compute_latest_signal,
    compute_signal_history,
)
from app.timeutil import ensure_utc, utcnow

telegram_router = APIRouter(prefix="/telegram", tags=["telegram"])
forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@telegram_router.get("/status")
def status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return tg.telegram_status(db)


@telegram_router.post("/test")
def send_test(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return tg.send_test_message(db)


@telegram_router.post("/notify")
def notify(
    symbol: str = Query("XAUUSD"),
    include_forecast: bool = Query(False),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return tg.notify_signal(db, symbol, include_forecast=include_forecast)


@telegram_router.get("/messages")
def messages(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, pattern="^(pending|sent|skipped|failed)$"),
    kind: str | None = Query(None, pattern="^(signal|forecast|test|system)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return tg.list_messages(db, limit=limit, offset=offset, status=status, kind=kind)


def _trade_forecast(db: Session, symbol: str) -> dict:
    sig = compute_latest_signal(db)
    signal = sig.get("signal", "NO_TRADE")
    p_long = float(sig.get("p_long", 0.0))
    p_short = float(sig.get("p_short", 0.0))
    raw = sig.get("bar_ts")
    if isinstance(raw, str):
        try:
            bar_ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            bar_ts = None
    else:
        bar_ts = ensure_utc(raw) if raw else None
    return {
        "symbol": symbol,
        "timeframe": "M15",
        "signal": signal,
        "direction": signal,
        "probability_long": p_long,
        "probability_short": p_short,
        "confidence": max(p_long, p_short),
        "threshold": sig.get("threshold"),
        "stale": sig.get("stale"),
        "bar_ts": bar_ts.isoformat() if bar_ts else None,
        "target_ts": (bar_ts + timedelta(minutes=15)).isoformat() if bar_ts else None,
        "model_version_id": sig.get("model_version_id"),
        "note": "Forecast = current trade_ens signal. Only LONG / SHORT / NO_TRADE.",
    }


def _forecast_stats(db: Session, symbol: str) -> dict:
    try:
        hist = compute_signal_history(db, limit=500)
    except TradeSignalError:
        return {"total": 0, "by_signal": {}, "metrics": None}
    bars = hist.get("bars", [])
    counts: dict[str, int] = {"LONG": 0, "SHORT": 0, "NO_TRADE": 0}
    for bar in bars:
        sig = bar.get("signal", "NO_TRADE")
        counts[sig] = counts.get(sig, 0) + 1
    return {
        "total": len(bars),
        "by_signal": counts,
        "metrics": hist.get("metrics"),
        "note": "Counts are trade_ens signals, not regime labels.",
    }


@forecast_router.get("/next")
def next_bar(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        payload = _trade_forecast(db, symbol)
        payload["stats"] = _forecast_stats(db, symbol)
        payload["generated_at"] = utcnow().isoformat()
        return payload
    except TradeSignalError as e:
        raise HTTPException(409, {"code": e.code, "message": str(e)})


@forecast_router.get("/stats")
def stats(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(2000, ge=10, le=10000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _forecast_stats(db, symbol)


@forecast_router.post("/score")
def score(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {
        "scored": 0,
        "note": "trade_ens history is computed on demand; no separate forecast table.",
    }


@forecast_router.get("/history")
def history(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        hist = compute_signal_history(db, limit=min(5000, offset + limit))
    except TradeSignalError as e:
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "forecasts": [],
            "reason_codes": [e.code],
        }
    bars = list(reversed(hist.get("bars", [])))[offset : offset + limit]
    return {
        "total": len(hist.get("bars", [])),
        "limit": limit,
        "offset": offset,
        "forecasts": [
            {
                "ts": b.get("ts"),
                "target_ts": b.get("ts"),
                "direction": b.get("signal", "NO_TRADE"),
                "signal": b.get("signal", "NO_TRADE"),
                "probability_up": b.get("p_long"),
                "probability_long": b.get("p_long"),
                "probability_short": b.get("p_short"),
                "confidence": max(float(b.get("p_long", 0)), float(b.get("p_short", 0))),
                "pending": False,
                "note": "trade_ens signal; no separate next-bar forecast model.",
            }
            for b in bars
        ],
    }
