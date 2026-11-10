"""Historical regime analysis service: background job + query helpers."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.history import HistoryConfig, build_segments, run_historical_inference
from app.ml.hmm_model import load_hmm_artifact
from app.ml.labels import make_labels
from app.ml.indicators import atr
from app.models import (
    MarketCandle,
    ModelVersion,
    RegimeHistoryBar,
    RegimeHistoryRun,
    RegimeSegment,
)
from app.services.training import load_candles
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.history")

BULK_CHUNK = 5000


class HistoryJobError(RuntimeError):
    pass


def _pick_source(db: Session, symbol: str) -> str:
    """Never mix brokers: prefer real FTMO data; fall back to labeled demo."""
    row = (
        db.query(MarketCandle.source)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == "M15")
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    return row[0] if row else "none"


def run_history_job(db: Session, run_id: int, cfg: HistoryConfig) -> dict:
    run = db.get(RegimeHistoryRun, run_id)
    if run is None:
        raise HistoryJobError("run not found")
    run.status = "running"
    run.started_at = utcnow()
    db.commit()

    hmm_version = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == "hmm", ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )
    rf_version = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == "random_forest", ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )
    if hmm_version is None or rf_version is None:
        raise HistoryJobError("No approved model pair — run training and approve first")
    if not hmm_version.artifact_path or not rf_version.artifact_path:
        raise HistoryJobError("Approved model artifacts missing on disk")

    hmm_artifact = load_hmm_artifact(Path(hmm_version.artifact_path))
    rf_model = joblib.load(Path(rf_version.artifact_path))
    engine_params = (hmm_version.metrics_json or {}).get("engine_params") or {}
    if not engine_params:
        raise HistoryJobError("HMM version has no engine_params in metrics")

    source = _pick_source(db, cfg.symbol)
    if source == "none":
        raise HistoryJobError("No candles available")
    run.data_source = source
    run.hmm_model_version_id = hmm_version.id
    run.rf_model_version_id = rf_version.id
    run.feature_version = hmm_artifact["meta"].get("feature_version", "v1")
    db.commit()

    df_m5, df_m15, df_h1 = load_candles(
        db, cfg.symbol, m5_limit=200_000, m15_limit=80_000, h1_limit=20_000, source=source
    )
    if len(df_m5) < 60 or len(df_m15) < 60 or len(df_h1) < 60:
        raise HistoryJobError("Insufficient candles (need >= 60 bars each TF)")

    bars = run_historical_inference(df_m5, df_m15, df_h1, hmm_artifact, rf_model, engine_params)
    segments = build_segments(
        bars,
        timeframe_seconds(cfg.timeframe),
        gap_split_multiple=cfg.gap_split_multiple,
        touch_tolerance=cfg.touch_tolerance,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        model_version_id=hmm_version.id,
    )
    if len(bars) < 100:
        raise HistoryJobError(f"Too few inferred bars: {len(bars)}")

    run.data_start = ensure_utc(bars.index[0])
    run.data_end = ensure_utc(bars.index[-1])
    run.bar_count = len(bars)
    run.segment_count = len(segments)
    run.status = "done"
    run.finished_at = utcnow()
    db.commit()

    # delete previous bars/segments for this run (idempotent regenerate)
    db.query(RegimeHistoryBar).filter(RegimeHistoryBar.run_id == run_id).delete()
    db.query(RegimeSegment).filter(RegimeSegment.run_id == run_id).delete()
    db.commit()

    bar_rows = []
    for ts, row in bars.iterrows():
        bar_rows.append(
            {
                "run_id": run_id,
                "ts": ensure_utc(ts),
                "regime": row["regime"],
                "confidence": float(row["confidence"]),
                "permission": row["permission"],
                "hmm_state": int(row["hmm_state"]),
                "hmm_probs_json": [float(p) for p in row["hmm_posterior"]],
                "rf_probs_json": {k: float(v) for k, v in row["rf_probs"].items()},
                "reason_codes_json": list(row["reason_codes"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "atr_ratio": float(row["atr_ratio"]),
                "adx_norm": float(row["adx_norm"]),
                "efficiency_ratio": float(row["efficiency_ratio"]),
                "h1_trend_context": float(row["h1_trend_context"]),
                "m5_momentum": float(row["m5_momentum"]),
            }
        )
    for i in range(0, len(bar_rows), BULK_CHUNK):
        db.bulk_insert_mappings(RegimeHistoryBar, bar_rows[i : i + BULK_CHUNK])
    db.commit()

    for seg in segments:
        seg["run_id"] = run_id
        db.add(RegimeSegment(**seg))
    db.commit()

    return {
        "run_id": run_id,
        "status": "done",
        "bar_count": run.bar_count,
        "segment_count": run.segment_count,
        "data_start": run.data_start.isoformat(),
        "data_end": run.data_end.isoformat(),
        "data_source": source,
        "hmm_model_version_id": hmm_version.id,
        "rf_model_version_id": rf_version.id,
    }


# ---------------------------------------------------------------- queries

def get_run(db: Session, run_id: int) -> RegimeHistoryRun | None:
    return db.get(RegimeHistoryRun, run_id)


def load_run_bars(db: Session, run_id: int) -> pd.DataFrame:
    rows = (
        db.query(RegimeHistoryBar)
        .filter(RegimeHistoryBar.run_id == run_id)
        .order_by(RegimeHistoryBar.ts)
        .all()
    )
    return pd.DataFrame(
        [
            {
                "ts": ensure_utc(r.ts),
                "regime": r.regime,
                "confidence": r.confidence,
                "permission": r.permission,
                "hmm_state": r.hmm_state,
                "hmm_posterior": r.hmm_probs_json,
                "rf_probs": r.rf_probs_json,
                "reason_codes": r.reason_codes_json,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "atr_ratio": r.atr_ratio,
                "adx_norm": r.adx_norm,
                "efficiency_ratio": r.efficiency_ratio,
                "h1_trend_context": r.h1_trend_context,
                "m5_momentum": r.m5_momentum,
            }
            for r in rows
        ]
    ).set_index("ts")


def load_run_segments(db: Session, run_id: int) -> list[dict]:
    rows = (
        db.query(RegimeSegment)
        .filter(RegimeSegment.run_id == run_id)
        .order_by(RegimeSegment.segment_index)
        .all()
    )
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "segment_index": r.segment_index,
            "regime": r.regime,
            "start_ts": ensure_utc(r.start_ts).isoformat(),
            "end_ts": ensure_utc(r.end_ts).isoformat(),
            "bar_count": r.bar_count,
            "duration_minutes": r.duration_minutes,
            "start_price": r.start_price,
            "end_price": r.end_price,
            "high_price": r.high_price,
            "low_price": r.low_price,
            "net_change": r.net_change,
            "mfe": r.mfe,
            "mae": r.mae,
            "atr_mean": r.atr_mean,
            "adx_mean": r.adx_mean,
            "efficiency_mean": r.efficiency_mean,
            "hmm_probs": r.hmm_probs_json,
            "confidence_mean": r.confidence_mean,
            "model_version_id": r.model_version_id,
            "split_reason": r.split_reason,
            "range_touches_high": r.range_touches_high,
            "range_touches_low": r.range_touches_low,
        }
        for r in rows
    ]


def reference_labels(db: Session, run: RegimeHistoryRun, horizon: int = 12) -> pd.Series:
    """Realized-reference labels for evaluation (future data, evaluation only)."""
    rows = (
        db.query(MarketCandle)
        .filter(
            MarketCandle.symbol == run.symbol,
            MarketCandle.timeframe == run.timeframe,
            MarketCandle.source == run.data_source,
        )
        .order_by(MarketCandle.ts)
        .all()
    )
    if not rows:
        return pd.Series(dtype=object)
    close = pd.Series(
        [r.close for r in rows],
        index=pd.to_datetime([ensure_utc(r.ts) for r in rows], utc=True),
    )
    atr_series = atr(pd.DataFrame({"high": [r.high for r in rows], "low": [r.low for r in rows], "close": close.values}, index=close.index), 14)
    return make_labels(close, atr_series=atr_series, horizon=horizon, up_threshold_atr=0.75)
