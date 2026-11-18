"""trade_ens API — status, latest signal, in-sample history and training."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.ml.features_v2 import FEATURE_VERSION
from app.ml.profit_trader import BarrierConfig
from app.models import MarketCandle, ModelVersion, TrainingRun, User
from app.rate_limit import HEAVY_JOB_LIMIT, limiter
from app.services.source import active_source
from app.services.trade_signal import (
    TradeSignalError,
    compute_latest_signal,
    compute_signal_history,
)
from app.services.trade_training import get_approved_trade_model, run_trade_training
from app.services.worker import worker
from app.timeutil import ensure_utc, utcnow

trade_model_router = APIRouter(prefix="/trade-model", tags=["trade_ens"])


def _status_payload(row: ModelVersion) -> dict:
    metrics = row.metrics_json or {}
    final = metrics.get("final", {})
    meta = final.get("meta", {}) if isinstance(final, dict) else {}
    walk = metrics.get("walk_forward", {})
    return {
        "model_name": "trade_ens",
        "approved": True,
        "model_version_id": row.id,
        "version": row.version,
        "feature_version": FEATURE_VERSION,
        "artifact_path": row.artifact_path,
        "trained_until": meta.get("trained_until"),
        "threshold": meta.get("threshold"),
        "thresholds": meta.get("thresholds"),
        "allowed_sides": meta.get("allowed_sides", ["LONG", "SHORT"]),
        "quantile": meta.get("quantile"),
        "barrier": meta.get("barrier") or BarrierConfig().to_dict(),
        "walk_forward": {
            "passed": walk.get("passed"),
            "gate": walk.get("gate"),
            "oos_metrics": walk.get("oos_metrics"),
            "naive_win_rate": walk.get("naive_win_rate"),
            "holdout_rows": walk.get("holdout_rows"),
        },
        "holdout_metrics": final.get("holdout_metrics"),
        "warnings": metrics.get("warnings", []),
    }


@trade_model_router.get("/status")
def trade_model_status(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = get_approved_trade_model(db)
    if row is None:
        return {
            "model_name": "trade_ens",
            "approved": False,
            "code": "NO_APPROVED_MODEL",
            "feature_version": FEATURE_VERSION,
        }
    return _status_payload(row)


@trade_model_router.get("/deployability")
def trade_model_deployability(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicit deployment gate — research/demo vs live readiness.

    Risk limits are intentionally NOT evaluated here; the execution EA owns
    per-trade risk and max daily loss. This endpoint only checks model evidence
    and data freshness, and never turns a stale/no-model state into "ready".
    """
    row = get_approved_trade_model(db)
    if row is None:
        return {
            "model_name": "trade_ens",
            "approved": False,
            "demo_ready": False,
            "live_ready": False,
            "blockers": ["NO_APPROVED_MODEL"],
            "warnings": [],
        }
    metrics = row.metrics_json or {}
    walk = metrics.get("walk_forward", {}) or {}
    oos = walk.get("oos_metrics", {}) or {}
    gate = walk.get("gate", {}) or {}
    final = metrics.get("final", {}) or {}
    holdout = final.get("holdout_metrics", {}) or {}
    allowed = metrics.get("allowed_sides") or final.get("allowed_sides") or ["LONG", "SHORT"]
    model_ready = bool(
        walk.get("passed")
        and (oos.get("n") or 0) >= 300
        and (oos.get("mean_pnl") or 0) > 0
        and (oos.get("profit_factor") or 0) > 1
    )
    source = active_source(db, "XAUUSD", "M15")
    latest = (
        db.query(MarketCandle.ts)
        .filter(
            MarketCandle.symbol == "XAUUSD",
            MarketCandle.timeframe == "M15",
            MarketCandle.source == source,
        )
        .order_by(MarketCandle.ts.desc())
        .first()
        if source
        else None
    )
    latest_ts = ensure_utc(latest[0]) if latest else None
    age_minutes = round((utcnow() - latest_ts).total_seconds() / 60.0, 1) if latest_ts else None
    threshold_minutes = settings.max_age_minutes("M15")
    fresh = bool(age_minutes is not None and age_minutes <= threshold_minutes)
    blockers: list[str] = []
    warnings: list[str] = []
    if not model_ready:
        blockers.append("MODEL_GATE_NOT_PASSED")
    if source is None:
        blockers.append("NO_DATA_SOURCE")
    elif latest_ts is None:
        blockers.append("NO_M15_DATA")
    elif not fresh:
        blockers.append("DATA_STALE")
    if not holdout or (holdout.get("n") or 0) == 0:
        warnings.append("HOLDOUT_NO_TRADES")
    elif (holdout.get("mean_pnl") or 0) <= 0:
        warnings.append("HOLDOUT_NOT_PROFITABLE")
    if tuple(allowed) == ("SHORT",) or list(allowed) == ["SHORT"]:
        warnings.append("SHORT_ONLY")
    warnings.append("NO_FORWARD_SHADOW")
    return {
        "model_name": "trade_ens",
        "approved": True,
        "model_version_id": row.id,
        "version": row.version,
        "allowed_sides": list(allowed),
        "model_ready": model_ready,
        "demo_ready": model_ready,
        "live_ready": bool(model_ready and fresh),
        "data_fresh": fresh,
        "source": source,
        "latest_bar_ts": latest_ts.isoformat() if latest_ts else None,
        "data_age_minutes": age_minutes,
        "data_threshold_minutes": threshold_minutes,
        "oos_metrics": oos,
        "holdout_metrics": holdout,
        "gate": gate,
        "blockers": blockers,
        "warnings": warnings,
        "note": (
            "demo_ready is model evidence only; live_ready additionally requires fresh ftmo_mt5 data. "
            "Per-trade risk and max daily loss are the EA's responsibility, not this API's."
        ),
    }


@trade_model_router.get("/signal")
def trade_model_signal(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return compute_latest_signal(db)
    except TradeSignalError as e:
        status_code = 409 if e.code in ("NO_APPROVED_MODEL", "DEMO_DATA_NOT_SUPPORTED") else 503
        raise HTTPException(status_code, {"code": e.code, "message": str(e)})


@trade_model_router.get("/history")
def trade_model_history(
    limit: int = Query(1000, ge=1, le=5000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return compute_signal_history(db, limit=limit)
    except TradeSignalError as e:
        status_code = 409 if e.code in ("NO_APPROVED_MODEL", "DEMO_DATA_NOT_SUPPORTED") else 503
        raise HTTPException(status_code, {"code": e.code, "message": str(e)})


@trade_model_router.post("/train")
@limiter.limit(HEAVY_JOB_LIMIT)
def trade_model_train(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = TrainingRun(
        model_type="trade_ens",
        params_json={"barrier": BarrierConfig().to_dict()},
        dataset_json={"source": "ftmo_mt5", "feature_version": FEATURE_VERSION},
        feature_version=FEATURE_VERSION,
        status="pending",
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    job_id = worker.submit(
        "trade_training",
        {"run_id": run.id},
        lambda s: run_trade_training(s, run.id),
    )
    return {"status": "scheduled", "job_id": job_id, "run_id": run.id}


__all__ = ["trade_model_router"]
