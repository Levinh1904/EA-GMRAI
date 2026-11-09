"""Live regime inference — strictly causal.

Warm-up: the last WARMUP_BARS closed M15 bars are replayed through the
forward filter, then the final bar's filtered posterior is used. The
hysteresis engine state is persisted with the previous prediction.
Any failure (stale data, missing model, invalid features) yields
regime=UNKNOWN with explicit reason codes — never a fabricated signal.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features import ALL_FEATURES, build_features
from app.ml.hmm_model import hmm_filter_from_artifact, load_hmm_artifact, semantic_probabilities
from app.ml.regime_engine import PERMISSIONS, EngineParams, EngineState, combine_scores
from app.ml.rf_model import RF_FEATURE_NAMES, build_rf_features, semantic_probs_array
from app.models import MarketCandle, ModelPrediction, ModelVersion
from app.services.training import load_candles
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.prediction")

WARMUP_BARS = 500
M15_PERIOD = timeframe_seconds("M15")


class InferenceUnavailable(Exception):
    def __init__(self, reason: str, codes: list[str]):
        super().__init__(reason)
        self.reason = reason
        self.codes = codes


def _get_approved_version(db: Session, model_type: str) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == model_type, ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )


def _latest_candle_ts(db: Session, timeframe: str, symbol: str = "XAUUSD") -> datetime | None:
    row = (
        db.query(MarketCandle.ts)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe)
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    return ensure_utc(row[0]) if row else None


def _latest_candle_source(db: Session, symbol: str = "XAUUSD") -> str | None:
    row = (
        db.query(MarketCandle.source)
        .filter(MarketCandle.symbol == symbol, MarketCandle.timeframe == "M15")
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    return row[0] if row else None


def compute_latest_regime(db: Session, symbol: str = "XAUUSD") -> dict:
    now = utcnow()

    # 1. Freshness
    latest_ts = _latest_candle_ts(db, "M15", symbol)
    if latest_ts is None:
        raise InferenceUnavailable("No M15 candles available", ["NO_DATA"])
    age_minutes = (now - latest_ts).total_seconds() / 60.0
    if age_minutes > settings.max_age_minutes("M15") * 1.5:
        raise InferenceUnavailable(
            f"M15 data stale: {age_minutes:.0f} min old", ["STALE_DATA"]
        )

    # 2. Approved models
    hmm_version = _get_approved_version(db, "hmm")
    rf_version = _get_approved_version(db, "random_forest")
    if hmm_version is None or rf_version is None:
        raise InferenceUnavailable("No approved model pair", ["NO_APPROVED_MODEL"])
    if not hmm_version.artifact_path or not rf_version.artifact_path:
        raise InferenceUnavailable("Model artifacts missing", ["MISSING_ARTIFACT"])

    # 3. Features
    df_m5, df_m15, df_h1 = load_candles(db, symbol, m5_limit=1200, m15_limit=900, h1_limit=900)
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < 60:
        raise InferenceUnavailable(f"Not enough feature rows: {len(features)}", ["INSUFFICIENT_FEATURES"])
    feature_ts = features.index[-1]
    data_timestamp = ensure_utc(feature_ts) + timedelta(seconds=M15_PERIOD)

    hmm_artifact = load_hmm_artifact(Path(hmm_version.artifact_path))
    hmm_cols = hmm_artifact["feature_columns"]
    scaler_mean = np.array(hmm_artifact["scaler_mean"])
    scaler_std = np.array(hmm_artifact["scaler_std"])
    X_hmm_raw = features[hmm_cols].values.astype(np.float64)
    X_hmm = (X_hmm_raw - scaler_mean) / np.maximum(scaler_std, 1e-9)

    # 4. Causal warm-up replay through the forward filter
    hmm_filter = hmm_filter_from_artifact(hmm_artifact)
    posterior = hmm_filter.posterior(X_hmm[-WARMUP_BARS:])
    posterior_row = posterior[-1]
    mapping = hmm_artifact["state_mapping"]
    hmm_semantic = semantic_probabilities(posterior_row, mapping)

    # 5. RF features for the last bar
    rf_model = joblib.load(Path(rf_version.artifact_path))
    warm_features = features.iloc[-WARMUP_BARS:]
    semantic_df = semantic_probs_array(posterior, mapping)
    rf_X = build_rf_features(
        posterior,
        np.array(hmm_artifact["params"]["transmat"]),
        mapping,
        warm_features,
        semantic_df,
    )
    rf_X = rf_X[RF_FEATURE_NAMES]
    rf_probs = rf_model.predict_proba(rf_X.iloc[[-1]].values)[0]
    rf_probs_dict = {}
    for i, c in enumerate(rf_model.classes_):
        rf_probs_dict[str(c)] = float(rf_probs[i])

    # 6. Engine (restore hysteresis state from previous prediction)
    metrics = hmm_version.metrics_json or {}
    engine_params = EngineParams(**{k: v for k, v in (metrics.get("engine_params") or {}).items() if k in EngineParams.__dataclass_fields__})
    engine = EngineState(engine_params)
    prev_pred = (
        db.query(ModelPrediction)
        .filter(ModelPrediction.model_version_id == hmm_version.id)
        .order_by(ModelPrediction.id.desc())
        .first()
    )
    if prev_pred and (prev_pred.components_json or {}).get("engine_state"):
        engine.restore(prev_pred.components_json["engine_state"])

    combined = combine_scores(hmm_semantic, rf_probs_dict, engine_params.weight_hmm)
    out = engine.step(combined)
    regime = out["regime"]
    permission = PERMISSIONS.get(regime, "NO_TRADE")

    # 7. Persist
    pred = ModelPrediction(
        model_version_id=hmm_version.id,
        symbol=symbol,
        timeframe="M15",
        ts=ensure_utc(feature_ts),
        regime=regime,
        confidence=out["confidence"],
        probabilities_json={
            "hmm_semantic": hmm_semantic,
            "rf": rf_probs_dict,
            "combined": {k: round(float(v), 6) for k, v in combined.items()},
        },
        components_json={
            "hmm_state": int(posterior_row.argmax()),
            "hmm_posterior": [round(float(p), 6) for p in posterior_row],
            "engine_state": out["engine_state"],
            "model_versions": {"hmm": hmm_version.id, "rf": rf_version.id},
        },
        reason_codes_json=out["reason_codes"],
        permission=permission,
        expiry_ts=ensure_utc(feature_ts) + timedelta(seconds=2 * M15_PERIOD),
        data_timestamp=data_timestamp,
    )
    db.add(pred)
    db.commit()

    return {
        "symbol": symbol,
        "timeframe": "M15",
        "timestamp": ensure_utc(feature_ts).isoformat(),
        "regime": regime,
        "confidence": out["confidence"],
        "probabilities": {
            "hmm_semantic": {k: round(float(v), 6) for k, v in hmm_semantic.items()},
            "rf": rf_probs_dict,
        },
        "model_version": hmm_version.id,
        "feature_version": hmm_artifact["meta"].get("feature_version"),
        "data_timestamp": data_timestamp.isoformat(),
        "data_source": _latest_candle_source(db, symbol),
        "expiry": pred.expiry_ts.isoformat(),
        "reason_codes": out["reason_codes"],
        "permission": permission,
        "data_age_minutes": round(age_minutes, 1),
    }


def regime_latest(db: Session, symbol: str = "XAUUSD") -> dict:
    """Public payload: never raises — degraded states return UNKNOWN."""
    try:
        return compute_latest_regime(db, symbol)
    except InferenceUnavailable as e:
        return {
            "symbol": symbol,
            "timeframe": "M15",
            "timestamp": utcnow().isoformat(),
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "probabilities": {},
            "model_version": None,
            "feature_version": None,
            "data_timestamp": None,
            "expiry": None,
            "reason_codes": e.codes,
            "permission": "NO_TRADE",
            "degraded_reason": e.reason,
        }
    except Exception as e:  # inference failure -> UNKNOWN, never a fake signal
        logger.exception("Regime inference failed")
        return {
            "symbol": symbol,
            "timeframe": "M15",
            "timestamp": utcnow().isoformat(),
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "probabilities": {},
            "model_version": None,
            "feature_version": None,
            "data_timestamp": None,
            "expiry": None,
            "reason_codes": ["INFERENCE_FAILED"],
            "permission": "NO_TRADE",
            "degraded_reason": str(e),
        }
