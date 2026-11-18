"""Telegram notifications + next-bar forecast API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import User
from app.services import telegram as tg
from app.services.forecast import forecast_next_bar, forecast_stats, score_pending_forecasts
from app.timeutil import utcnow

telegram_router = APIRouter(prefix="/telegram", tags=["telegram"])
forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@telegram_router.get("/status")
def status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Configuration + delivery counts (read from the message log)."""
    return tg.telegram_status(db)


@telegram_router.post("/test")
def send_test(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin-only connectivity check."""
    return tg.send_test_message(db)


@telegram_router.post("/notify")
def notify(
    symbol: str = Query("XAUUSD"),
    include_forecast: bool = Query(True),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Send the latest signal if it is new; repeats are logged as `skipped`."""
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
    """Full message history with filters — the audit trail of every attempt."""
    return tg.list_messages(db, limit=limit, offset=offset, status=status, kind=kind)


@forecast_router.get("/next")
def next_bar(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Directional forecast for the next M15 bar (from the last closed bar)."""
    try:
        payload = forecast_next_bar(db, symbol)
    except ValueError as e:
        raise HTTPException(400, str(e))
    payload["stats"] = forecast_stats(db, symbol)
    payload["generated_at"] = utcnow().isoformat()
    return payload


@forecast_router.get("/stats")
def stats(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(2000, ge=10, le=10000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Live accuracy of this system's own stored forecasts."""
    return forecast_stats(db, symbol, limit=limit)


@forecast_router.post("/score")
def score(
    symbol: str = Query("XAUUSD"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Fill in outcomes for forecasts whose target bar has closed."""
    return score_pending_forecasts(db, symbol)


@forecast_router.get("/history")
def history(
    symbol: str = Query("XAUUSD"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent forecasts with their realised outcome (correct / wrong / pending)."""
    from app.models import BarForecast
    from app.timeutil import ensure_utc

    q = db.query(BarForecast).filter(BarForecast.symbol == symbol)
    total = q.count()
    rows = q.order_by(BarForecast.ts.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "forecasts": [
            {
                "id": r.id,
                "ts": ensure_utc(r.ts).isoformat(),
                "target_ts": ensure_utc(r.target_ts).isoformat(),
                "direction": r.direction,
                "probability_up": r.probability_up,
                "confidence": r.confidence,
                "regime": r.regime,
                "actual_direction": r.actual_direction,
                "actual_open": r.actual_open,
                "actual_close": r.actual_close,
                "correct": r.correct,
                "pending": r.correct is None,
            }
            for r in rows
        ],
    }
