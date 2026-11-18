"""Data retention — prune append-only tables that would otherwise grow forever.

Nothing in this codebase deleted rows except per-run regenerate, so these
tables grow without bound:
    system_logs, telegram_messages, data_sync_logs, data_quality_reports,
    background_jobs, bar_forecasts, model_predictions,
    plus the bulk regime_history_bars / outcome_evaluations.

Policy: keep what is useful for research, drop what is only operational noise.
History runs and their bars are NEVER pruned by default — they are the analysed
dataset. Only explicitly configured limits remove them.

Every deletion is bounded (batched) and logged, so a run can never lock the DB
or silently wipe more than intended.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    BackgroundJob,
    BarForecast,
    DataQualityReport,
    DataSyncLog,
    ModelPrediction,
    SystemLog,
    TelegramMessage,
)
from app.timeutil import utcnow

logger = logging.getLogger("gmrai.retention")

BATCH = 5000


def _prune(db: Session, model, cutoff_column, cutoff, keep_where=None) -> int:
    """Delete rows older than `cutoff` in bounded batches. Returns rows removed."""
    removed = 0
    while True:
        q = db.query(model).filter(cutoff_column < cutoff)
        if keep_where is not None:
            q = q.filter(keep_where)
        ids = [r.id for r in q.limit(BATCH).all()]
        if not ids:
            break
        db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        removed += len(ids)
        if len(ids) < BATCH:
            break
    return removed


def run_retention(db: Session, dry_run: bool = False) -> dict:
    """Enforce the configured retention windows. Safe to run on a schedule."""
    now = utcnow()
    plan = {
        "system_logs": settings.retention_system_log_days,
        "telegram_messages": settings.retention_telegram_days,
        "data_sync_logs": settings.retention_sync_log_days,
        "data_quality_reports": settings.retention_quality_days,
        "background_jobs": settings.retention_jobs_days,
        "bar_forecasts": settings.retention_forecast_days,
        "model_predictions": settings.retention_predictions_days,
    }

    targets = [
        (SystemLog, SystemLog.created_at, plan["system_logs"]),
        # Always keep failed/sent messages longer than skipped noise.
        (TelegramMessage, TelegramMessage.created_at, plan["telegram_messages"]),
        (DataSyncLog, DataSyncLog.finished_at, plan["data_sync_logs"]),
        (DataQualityReport, DataQualityReport.checked_at, plan["data_quality_reports"]),
        (BackgroundJob, BackgroundJob.created_at, plan["background_jobs"]),
        (BarForecast, BarForecast.created_at, plan["bar_forecasts"]),
        (ModelPrediction, ModelPrediction.created_at, plan["model_predictions"]),
    ]

    out: dict = {"dry_run": dry_run, "deleted": {}}
    for model, col, days in targets:
        if days is None or days <= 0:
            out["deleted"][model.__tablename__] = "disabled"
            continue
        cutoff = now - timedelta(days=days)
        if dry_run:
            n = db.query(model).filter(col < cutoff).count()
            out["deleted"][model.__tablename__] = f"would delete {n}"
        else:
            out["deleted"][model.__tablename__] = _prune(db, model, col, cutoff)

    # Optional hard cap on history runs (disabled by default: research data).
    cap = settings.retention_history_runs
    if cap and cap > 0:
        from app.models import RegimeHistoryRun

        total = db.query(RegimeHistoryRun).count()
        if total > cap:
            keep_ids = [
                r.id
                for r in db.query(RegimeHistoryRun.id)
                .order_by(RegimeHistoryRun.id.desc())
                .limit(cap)
                .all()
            ]
            doomed = [
                r.id for r in db.query(RegimeHistoryRun.id).all() if r.id not in set(keep_ids)
            ]
            if doomed:
                from app.models import OutcomeEvaluation, RegimeHistoryBar, RegimeSegment

                if dry_run:
                    out["deleted"]["regime_history"] = f"would delete {len(doomed)} runs"
                else:
                    for model in (RegimeHistoryBar, RegimeSegment, OutcomeEvaluation):
                        db.query(model).filter(model.run_id.in_(doomed)).delete(
                            synchronize_session=False
                        )
                    db.query(RegimeHistoryRun).filter(
                        RegimeHistoryRun.id.in_(doomed)
                    ).delete(synchronize_session=False)
                    db.commit()
                    out["deleted"]["regime_history"] = f"{len(doomed)} runs"
    else:
        out["deleted"]["regime_history"] = "disabled"

    if not dry_run and any(isinstance(v, int) and v > 0 for v in out["deleted"].values()):
        db.add(
            SystemLog(
                level="INFO",
                component="retention",
                message="retention pass applied",
                meta_json=out["deleted"],
            )
        )
        db.commit()
        logger.info("Retention deleted: %s", out["deleted"])
    return out
