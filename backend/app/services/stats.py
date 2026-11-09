"""Dashboard statistics aggregation."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DataQualityReport,
    DataSyncLog,
    MarketCandle,
    ModelPrediction,
    ModelVersion,
)
from app.services.prediction import regime_latest
from app.timeutil import ensure_utc, utcnow


def dashboard_stats(db: Session, symbol: str = "XAUUSD") -> dict:
    now = utcnow()
    candle_stats = {}
    data_freshness = {}
    for tf in ("M5", "M15", "H1"):
        count = (
            db.query(func.count(MarketCandle.id))
            .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == tf)
            .scalar()
        ) or 0
        latest = (
            db.query(MarketCandle.ts)
            .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == tf)
            .order_by(MarketCandle.ts.desc())
            .first()
        )
        latest_ts = ensure_utc(latest[0]) if latest else None
        age = (now - latest_ts).total_seconds() / 60.0 if latest_ts else None
        candle_stats[tf] = {"count": int(count), "latest_ts": latest_ts.isoformat() if latest_ts else None}
        data_freshness[tf] = {
            "age_minutes": round(age, 1) if age is not None else None,
            "stale": age is not None and age > settings.max_age_minutes(tf),
            "threshold_minutes": settings.max_age_minutes(tf),
        }

    last_sync = (
        db.query(DataSyncLog).order_by(DataSyncLog.id.desc()).limit(10).all()
    )
    last_quality = (
        db.query(DataQualityReport)
        .order_by(DataQualityReport.id.desc())
        .limit(6)
        .all()
    )
    active_models = {
        "hmm": [
            {
                "id": v.id,
                "version": v.version,
                "version_id": v.id,
                "model_id": v.model_id,
                "created_at": v.created_at.isoformat(),
                "metrics": v.metrics_json,
            }
            for v in db.query(ModelVersion)
            .filter(ModelVersion.model_type == "hmm", ModelVersion.status == "approved")
            .order_by(ModelVersion.id.desc())
            .limit(1)
        ],
        "random_forest": [
            {
                "id": v.id,
                "version": v.version,
                "version_id": v.id,
                "model_id": v.model_id,
                "created_at": v.created_at.isoformat(),
                "metrics": v.metrics_json,
            }
            for v in db.query(ModelVersion)
            .filter(ModelVersion.model_type == "random_forest", ModelVersion.status == "approved")
            .order_by(ModelVersion.id.desc())
            .limit(1)
        ],
    }

    return {
        "symbol": symbol,
        "generated_at": now.isoformat(),
        "regime": regime_latest(db, symbol),
        "candles": candle_stats,
        "data_freshness": data_freshness,
        "last_sync": [
            {
                "id": s.id,
                "collector_id": s.collector_id,
                "timeframe": s.timeframe,
                "finished_at": ensure_utc(s.finished_at).isoformat() if s.finished_at else None,
                "status": s.status,
                "inserted": s.candles_inserted,
                "updated": s.candles_updated,
            }
            for s in last_sync
        ],
        "last_quality_reports": [
            {
                "id": q.id,
                "timeframe": q.timeframe,
                "checked_at": ensure_utc(q.checked_at).isoformat() if q.checked_at else None,
                "total_candles": q.total_candles,
                "gap_count": q.gap_count,
                "duplicate_count": q.duplicate_count,
                "bad_candle_count": q.bad_candle_count,
                "stale": bool((q.report_json or {}).get("stale")),
            }
            for q in last_quality
        ],
        "active_models": active_models,
    }
