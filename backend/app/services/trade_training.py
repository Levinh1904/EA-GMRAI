"""Training pipeline for the trade_ens model (current project integration)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features_v2 import FEATURE_VERSION, build_features_v2
from app.ml.profit_trader import BarrierConfig, barrier_outcomes
from app.ml.trade_model import (
    DEFAULT_ALLOWED_SIDES,
    MIN_FEATURE_ROWS,
    MODEL_NAME,
    TradeModelError,
    build_dataset,
    run_walk_forward,
    train_final_model,
)
from app.models import ModelVersion, TrainingRun
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import utcnow


class TradeTrainingError(ValueError):
    pass


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def run_trade_training(db: Session, run_id: int | None = None) -> dict:
    """Load real ftmo_mt5 candles, train/evaluate trade_ens, register result."""
    run = db.get(TrainingRun, run_id) if run_id is not None else None
    if run is not None:
        run.status = "running"
        run.started_at = utcnow()
        run.feature_version = FEATURE_VERSION
        db.commit()

    try:
        source = active_source(db, "XAUUSD", "M15")
        if source != "ftmo_mt5":
            raise TradeTrainingError(
                "No real ftmo_mt5 source available; synthetic_demo is not accepted for training"
            )
        df_m5, df_m15, df_h1 = load_candles(
            db,
            "XAUUSD",
            m5_limit=200_000,
            m15_limit=80_000,
            h1_limit=20_000,
            source="ftmo_mt5",
        )
        if len(df_m15) < 1000:
            raise TradeTrainingError(f"Not enough M15 candles: {len(df_m15)}")

        features = build_features_v2(df_m5, df_m15, df_h1)
        if len(features) < MIN_FEATURE_ROWS:
            raise TradeTrainingError(
                f"Not enough feature rows: {len(features)} < {MIN_FEATURE_ROWS}; "
                "collect more ftmo_mt5 history (synthetic_demo is rejected)"
            )
        outcomes = barrier_outcomes(df_m15)
        ds = build_dataset(features, outcomes)
        if len(ds) < MIN_FEATURE_ROWS:
            raise TradeTrainingError(
                f"Not enough valid barrier rows: {len(ds)} < {MIN_FEATURE_ROWS}"
            )

        cfg = BarrierConfig()
        walk = run_walk_forward(ds, cfg, allowed_sides=DEFAULT_ALLOWED_SIDES)
        final = train_final_model(ds, cfg, allowed_sides=DEFAULT_ALLOWED_SIDES) if walk["folds"] else {
            "passed": False, "reason": "no_folds"
        }
        passed = bool(walk.get("passed")) and bool(final.get("passed")) and final.get("model") is not None

        artifact_path = None
        if passed:
            artifact_dir = Path(settings.artifact_dir) / MODEL_NAME / utcnow().strftime("%Y%m%dT%H%M%S")
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_dir / "model.joblib"
            joblib.dump(
                {
                    "model": final["model"],
                    "threshold": final["threshold"],
                    "meta": final["meta"],
                },
                artifact_path,
            )

        metrics = {
            "walk_forward": _jsonable(walk),
            "final": _jsonable({k: v for k, v in final.items() if k != "model"}),
            "passed": passed,
            "allowed_sides": list(DEFAULT_ALLOWED_SIDES),
            "warnings": [
                "Win rate is not profit: TP=0.5 ATR is smaller than SL=2.0 ATR.",
                "Reference benchmark is not a target; this run reports actual data only.",
                "Holdout is evaluated once and is not used to choose the threshold.",
                "The side filter was selected on walk-forward selection slices only; "
                "SHORT-only is not a guarantee that LONG will lose in the future.",
            ],
        }
        oos = walk.get("oos_metrics") or {}
        if oos.get("n", 0) and oos.get("mean_pnl", 0) <= 0:
            metrics["warnings"].append(
                "OOS mean PnL is <= 0 even though the win-rate gate passed; "
                "do not present this as profitable and do not trade it live."
            )
        holdout = (final.get("holdout_metrics") or {}) if isinstance(final, dict) else {}
        if final.get("passed") and not holdout.get("n", 0):
            metrics["warnings"].append(
                "Final holdout produced no trades at the frozen threshold; "
                "there is no holdout PnL evidence for this model version."
            )
        version_no = (
            db.query(ModelVersion)
            .filter(ModelVersion.model_type == MODEL_NAME)
            .count()
            + 1
        )
        mv = ModelVersion(
            model_type=MODEL_NAME,
            model_id=1,
            version=version_no,
            status="approved" if passed else "rejected",
            metrics_json=metrics,
            artifact_path=str(artifact_path) if artifact_path else None,
            created_at=utcnow(),
        )
        db.add(mv)
        if run is not None:
            run.status = "done"
            run.finished_at = utcnow()
            run.dataset_json = {
                "source": source,
                "feature_version": FEATURE_VERSION,
                "feature_rows": int(len(features)),
                "valid_rows": int(len(ds)),
                "data_start": str(ds.index.min()) if len(ds) else None,
                "data_end": str(ds.index.max()) if len(ds) else None,
            }
            run.metrics_json = metrics
            run.params_json = {"barrier": cfg.to_dict()}
        db.commit()
        return {"model_version_id": mv.id, "passed": passed, "metrics": metrics}
    except Exception as exc:
        if run is not None:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"[:1000]
            run.finished_at = utcnow()
            db.commit()
        raise


def get_approved_trade_model(db: Session):
    """Latest approved trade_ens artifact, or None."""
    row = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == MODEL_NAME, ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )
    if row is None:
        return None
    if not row.artifact_path or not Path(row.artifact_path).exists():
        return None
    return row
