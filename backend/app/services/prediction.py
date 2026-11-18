"""Live regime inference — strictly causal and idempotent per bar.

Warm-up: the last WARMUP_BARS closed M15 bars are replayed through the
forward filter, then the final bar's filtered posterior is used. The
hysteresis engine state is persisted with the previous prediction.

Idempotency: exactly ONE prediction row exists per (model_version, bar). A
repeated poll for an already-predicted bar returns the stored row and does NOT
run the engine again, so `up_confirm` / `exit_count` can never advance twice on
the same candle (constraint `uq_pred_bar` enforces this across processes).

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features import build_features
from app.ml.hmm_model import hmm_filter_from_artifact, load_hmm_artifact, semantic_probabilities
from app.ml.regime_engine import PERMISSIONS, EngineParams, EngineState, combine_scores
from app.ml.rf_model import RF_FEATURE_NAMES, build_rf_features, semantic_probs_array
from app.models import MarketCandle, ModelPrediction, ModelVersion
from app.services.registry import get_active_approved_pair
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.prediction")

WARMUP_BARS = 1000
M15_PERIOD = timeframe_seconds("M15")


class InferenceUnavailable(Exception):
    def __init__(self, reason: str, codes: list[str]):
        super().__init__(reason)
        self.reason = reason
        self.codes = codes


def _latest_candle_ts(
    db: Session, timeframe: str, symbol: str = "XAUUSD", source: str | None = None
) -> datetime | None:
    q = db.query(MarketCandle.ts).filter(
        MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe
    )
    if source:
        q = q.filter(MarketCandle.source == source)
    row = q.order_by(MarketCandle.ts.desc()).first()
    return ensure_utc(row[0]) if row else None


def _market_is_closed(now: datetime, last_bar_open: datetime) -> bool:
    """True when the gold market is closed (weekend) and the last bar is final.

    XAUUSD trades ~Sun 22:00 UTC → Fri 21:00 UTC. When the newest candle is more
    than a session behind, no new bar can arrive until the market reopens, so a
    stale timestamp means "closed", not "broken".
    """
    if (now - ensure_utc(last_bar_open)).total_seconds() < 4 * 3600:
        return False
    return now.weekday() >= 5  # 5=Sat, 6=Sun


def _find_prediction(
    db: Session, version_id: int, symbol: str, ts: datetime
) -> ModelPrediction | None:
    return (
        db.query(ModelPrediction)
        .filter(
            ModelPrediction.model_version_id == version_id,
            ModelPrediction.symbol == symbol,
            ModelPrediction.timeframe == "M15",
            ModelPrediction.ts == ts,
        )
        .first()
    )


def _payload_from_row(
    pred: ModelPrediction,
    hmm_version: ModelVersion,
    feature_version: str | None,
    source: str | None,
    age_minutes: float,
) -> dict:
    """Rebuild the API payload from a persisted prediction (no re-inference)."""
    probs = pred.probabilities_json or {}
    return {
        "symbol": pred.symbol,
        "timeframe": pred.timeframe,
        "timestamp": ensure_utc(pred.ts).isoformat(),
        "regime": pred.regime,
        "confidence": pred.confidence,
        "probabilities": {
            "hmm_semantic": probs.get("hmm_semantic", {}),
            "rf": probs.get("rf", {}),
        },
        "model_version": hmm_version.id,
        "feature_version": feature_version,
        "data_timestamp": (
            ensure_utc(pred.data_timestamp).isoformat() if pred.data_timestamp else None
        ),
        "data_source": source,
        "expiry": ensure_utc(pred.expiry_ts).isoformat() if pred.expiry_ts else None,
        "reason_codes": pred.reason_codes_json or [],
        "permission": pred.permission,
        "data_age_minutes": round(age_minutes, 1),
        "cached": True,
    }


def compute_latest_regime(db: Session, symbol: str = "XAUUSD") -> dict:
    now = utcnow()
    source = active_source(db, symbol, "M15")
    if source is None:
        raise InferenceUnavailable("No M15 candles available", ["NO_DATA"])

    # 1. Freshness (single source — never compare across feeds)
    latest_ts = _latest_candle_ts(db, "M15", symbol, source)
    if latest_ts is None:
        raise InferenceUnavailable("No M15 candles available", ["NO_DATA"])
    age_minutes = (now - latest_ts).total_seconds() / 60.0
    stale = age_minutes > settings.max_age_minutes("M15") * 1.5

    # 2. Approved models
    pair = get_active_approved_pair(db)
    if pair is None:
        raise InferenceUnavailable("No approved model pair", ["NO_APPROVED_MODEL"])
    hmm_version, rf_version = pair
    if not hmm_version.artifact_path or not rf_version.artifact_path:
        raise InferenceUnavailable("Model artifacts missing", ["MISSING_ARTIFACT"])

    hmm_artifact = load_hmm_artifact(Path(hmm_version.artifact_path))
    feature_version = hmm_artifact["meta"].get("feature_version")

    # 3. Idempotency fast path — this bar is already predicted for this version.
    #
    # This runs BEFORE the staleness rejection on purpose: once the market closes
    # (weekend / session gap) there is nothing new to infer, but the last closed
    # bar still HAS a valid, already-computed regime. Returning UNKNOWN there
    # would throw away real analysis and make the UI look broken.
    existing = _find_prediction(db, hmm_version.id, symbol, latest_ts)
    if existing is not None:
        payload = _payload_from_row(existing, hmm_version, feature_version, source, age_minutes)
        if stale:
            payload["stale"] = True
            payload["market_closed"] = _market_is_closed(now, latest_ts)
            payload["reason_codes"] = list(payload.get("reason_codes") or []) + ["STALE_DATA"]
        return payload

    if stale:
        raise InferenceUnavailable(f"M15 data stale: {age_minutes:.0f} min old", ["STALE_DATA"])

    # 4. Features
    df_m5, df_m15, df_h1 = load_candles(
        db, symbol, m5_limit=1500, m15_limit=1500, h1_limit=1500, source=source
    )
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < 60:
        raise InferenceUnavailable(
            f"Not enough feature rows: {len(features)}", ["INSUFFICIENT_FEATURES"]
        )
    feature_ts = ensure_utc(features.index[-1])
    data_timestamp = feature_ts + timedelta(seconds=M15_PERIOD)

    # Same bar may differ from latest raw candle if trailing features are NaN.
    existing = _find_prediction(db, hmm_version.id, symbol, feature_ts)
    if existing is not None:
        return _payload_from_row(existing, hmm_version, feature_version, source, age_minutes)

    hmm_cols = hmm_artifact["feature_columns"]
    scaler_mean = np.array(hmm_artifact["scaler_mean"])
    scaler_std = np.array(hmm_artifact["scaler_std"])
    X_hmm_raw = features[hmm_cols].values.astype(np.float64)
    X_hmm = (X_hmm_raw - scaler_mean) / np.maximum(scaler_std, 1e-9)

    # 5. Causal warm-up replay through the forward filter
    hmm_filter = hmm_filter_from_artifact(hmm_artifact)
    posterior = hmm_filter.posterior(X_hmm[-WARMUP_BARS:])
    posterior_row = posterior[-1]
    mapping = hmm_artifact["state_mapping"]
    hmm_semantic = semantic_probabilities(posterior_row, mapping)

    # 6. RF features for the last bar
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

    # 7. Engine (restore hysteresis state from the previous BAR, not the last poll)
    metrics = hmm_version.metrics_json or {}
    engine_params = EngineParams(
        **{
            k: v
            for k, v in (metrics.get("engine_params") or {}).items()
            if k in EngineParams.__dataclass_fields__
        }
    )
    engine = EngineState(engine_params)
    prev_pred = (
        db.query(ModelPrediction)
        .filter(
            ModelPrediction.model_version_id == hmm_version.id,
            ModelPrediction.symbol == symbol,
            ModelPrediction.timeframe == "M15",
            ModelPrediction.ts < feature_ts,
        )
        .order_by(ModelPrediction.ts.desc())
        .first()
    )
    if prev_pred and (prev_pred.components_json or {}).get("engine_state"):
        engine.restore(prev_pred.components_json["engine_state"])

    combined = combine_scores(hmm_semantic, rf_probs_dict, engine_params.weight_hmm)

    # Causal current-state detection: lets the engine report a trend that is
    # already in progress instead of holding SIDEWAYS until the (future-labelled)
    # models catch up.
    from app.ml.state_detector import compute_state_inputs, detect_state

    state_inputs = compute_state_inputs(df_m15).reindex(features.index)
    state_name: str | None = None
    state_strength = 0.0
    state_reason: str | None = None
    if feature_ts in state_inputs.index:
        si = state_inputs.loc[feature_ts]
        state_name, state_strength, state_reason = detect_state(
            si["displacement"], si["slope"], si["adx_norm"]
        )
        combined["state"] = state_name
        combined["state_strength"] = state_strength
        combined["state_displacement"] = float(si["displacement"])
    combined["h1_trend_context"] = float(features["h1_trend_context"].iloc[-1])
    combined["hour_utc"] = int(feature_ts.hour)

    out = engine.step(combined)
    raw_regime = out["regime"]
    regime = out["regime"]

    # Same short-trend filter the history/day analysis applies.
    #
    # Without this, a 2-bar "trend" is published live (and alerted on Telegram)
    # while the history page relabels those very bars SIDEWAYS — the same bar
    # showing two different regimes depending on where you look, which reads as
    # tampering. CAUSAL: only preceding bars are consulted, never later ones.
    if engine_params.min_signal_bars > 1:
        from app.ml.regime_engine import _trend_of

        direction = _trend_of(regime)
        if direction is not None:
            prior = (
                db.query(ModelPrediction.regime, ModelPrediction.components_json)
                .filter(
                    ModelPrediction.model_version_id == hmm_version.id,
                    ModelPrediction.symbol == symbol,
                    ModelPrediction.timeframe == "M15",
                    ModelPrediction.ts < feature_ts,
                )
                .order_by(ModelPrediction.ts.desc())
                .limit(engine_params.min_signal_bars)
                .all()
            )
            run_len = 1
            for prev_regime, comp in prior:
                # Use the RAW engine regime, never the already-collapsed one:
                # otherwise bar 1 is stored SIDEWAYS, bar 2 sees SIDEWAYS and the
                # run can never reach min_signal_bars (self-locking bug).
                raw_prev = (comp or {}).get("raw_regime") or prev_regime
                if _trend_of(raw_prev) != direction:
                    break
                run_len += 1
            if run_len < engine_params.min_signal_bars:
                regime = "SIDEWAYS"
                out["reason_codes"] = list(out["reason_codes"]) + ["SHORT_TREND_COLLAPSED"]
    permission = PERMISSIONS.get(regime, "NO_TRADE")

    # 8. Persist exactly once per bar
    pred = ModelPrediction(
        model_version_id=hmm_version.id,
        symbol=symbol,
        timeframe="M15",
        ts=feature_ts,
        regime=regime,
        confidence=out["confidence"],
        probabilities_json={
            "hmm_semantic": hmm_semantic,
            "rf": rf_probs_dict,
            # Only the numeric score fields belong here — `combined` also
            # carries the detector's string state, stored under components.
            "combined": {
                k: round(float(v), 6)
                for k, v in combined.items()
                if isinstance(v, (int, float))
            },
        },
        components_json={
            "hmm_state": int(posterior_row.argmax()),
            "hmm_posterior": [round(float(p), 6) for p in posterior_row],
            "engine_state": out["engine_state"],
            "raw_regime": raw_regime,
            "model_versions": {"hmm": hmm_version.id, "rf": rf_version.id},
            "data_source": source,
            "detected_state": state_name,
            "detected_state_strength": round(state_strength, 4),
            "detected_state_reason": state_reason,
        },
        reason_codes_json=out["reason_codes"],
        permission=permission,
        expiry_ts=feature_ts + timedelta(seconds=2 * M15_PERIOD),
        data_timestamp=data_timestamp,
    )
    db.add(pred)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent worker inserted this bar first — reuse it, never double-step.
        db.rollback()
        existing = _find_prediction(db, hmm_version.id, symbol, feature_ts)
        if existing is None:
            raise
        return _payload_from_row(existing, hmm_version, feature_version, source, age_minutes)

    return {
        "symbol": symbol,
        "timeframe": "M15",
        "timestamp": feature_ts.isoformat(),
        "regime": regime,
        "confidence": out["confidence"],
        "probabilities": {
            "hmm_semantic": {k: round(float(v), 6) for k, v in hmm_semantic.items()},
            "rf": rf_probs_dict,
        },
        "model_version": hmm_version.id,
        "feature_version": feature_version,
        "data_timestamp": data_timestamp.isoformat(),
        "data_source": source,
        "expiry": pred.expiry_ts.isoformat(),
        "reason_codes": out["reason_codes"],
        "permission": permission,
        "data_age_minutes": round(age_minutes, 1),
        "cached": False,
        "detected_state": state_name,
        "detected_state_strength": round(state_strength, 4),
        "detected_state_reason": state_reason,
    }


def _persist_prediction(
    db: Session,
    pred: ModelPrediction,
    hmm_version: ModelVersion,
    symbol: str,
    ts: datetime,
) -> bool:
    """Insert one prediction row. Returns False if this bar already has one."""
    db.add(pred)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        if _find_prediction(db, hmm_version.id, symbol, ts) is None:
            raise
        return False


def backfill_predictions(
    db: Session,
    symbol: str = "XAUUSD",
    max_bars: int = 500,
) -> dict:
    """Score every CLOSED M15 bar that has no prediction yet.

    `compute_latest_regime` only ever scores the newest bar. If the app was down
    (or nobody polled) when a candle closed, that bar never gets a label — a
    6-hour outage silently leaves ~24 unlabelled bars, which is exactly why the
    chart showed a gap in the AI bands. This replays the missing bars in order so
    the engine's hysteresis state advances once per bar, exactly as it would have
    live.

    Causal and idempotent: each bar is scored using only data up to that bar, and
    existing rows are never overwritten.
    """
    source = active_source(db, symbol, "M15")
    if source is None:
        return {"scored": 0, "reason": "NO_DATA"}

    pair = get_active_approved_pair(db)
    if pair is None or not pair[0].artifact_path:
        return {"scored": 0, "reason": "NO_APPROVED_MODEL"}
    hmm_version, rf_version = pair

    have = {
        ensure_utc(r[0])
        for r in db.query(ModelPrediction.ts)
        .filter(
            ModelPrediction.model_version_id == hmm_version.id,
            ModelPrediction.symbol == symbol,
            ModelPrediction.timeframe == "M15",
        )
        .all()
    }

    # Only bars that are actually closed: the newest candle is the last finished
    # one (the collector never stores a forming bar), so every candle is eligible.
    candle_ts = [
        ensure_utc(r[0])
        for r in db.query(MarketCandle.ts)
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == "M15",
            MarketCandle.source == source,
        )
        .order_by(MarketCandle.ts.desc())
        .limit(3000)
        .all()
    ]
    missing = sorted(t for t in candle_ts if t not in have)
    if not missing:
        return {"scored": 0, "reason": "UP_TO_DATE", "missing": 0}

    # Warm up once, then walk forward one bar at a time so the HMM filter and the
    # engine state advance causally for every bar that was skipped.
    df_m5, df_m15, df_h1 = load_candles(
        db, symbol, m5_limit=1500, m15_limit=1500, h1_limit=1500, source=source
    )
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < 60:
        return {"scored": 0, "reason": "INSUFFICIENT_FEATURES"}

    hmm_artifact = load_hmm_artifact(Path(hmm_version.artifact_path))
    feature_version = hmm_artifact["meta"].get("feature_version")
    hmm_cols = hmm_artifact["feature_columns"]
    scaler_mean = np.array(hmm_artifact["scaler_mean"])
    scaler_std = np.array(hmm_artifact["scaler_std"])
    mapping = hmm_artifact["state_mapping"]
    transmat = np.array(hmm_artifact["params"]["transmat"])

    X_hmm_raw = features[hmm_cols].values.astype(np.float64)
    X_hmm = (X_hmm_raw - scaler_mean) / np.maximum(scaler_std, 1e-9)
    hmm_filter = hmm_filter_from_artifact(hmm_artifact)
    posterior = hmm_filter.posterior(X_hmm[-WARMUP_BARS:])
    warm_index = features.index[-len(posterior) :]
    warm_features = features.loc[warm_index]

    # Only bars the warm-up window can actually score. Filtering BEFORE slicing
    # means `max_bars` always buys real work instead of shrinking each pass.
    scoreable = set(warm_index)
    missing = [t for t in missing if t in scoreable]
    if not missing:
        return {"scored": 0, "reason": "OUTSIDE_FEATURE_WINDOW", "missing": 0}
    missing = missing[-max_bars:]

    # RF features are independent of engine state, so they can be computed for
    # the whole warm window once.
    semantic_df = semantic_probs_array(posterior, mapping)
    rf_model = joblib.load(Path(rf_version.artifact_path))
    rf_X = build_rf_features(
        posterior, transmat, mapping, warm_features, semantic_df
    )[RF_FEATURE_NAMES]
    rf_probs_all = rf_model.predict_proba(rf_X.values)

    metrics = hmm_version.metrics_json or {}
    engine_params = EngineParams(
        **{
            k: v
            for k, v in (metrics.get("engine_params") or {}).items()
            if k in EngineParams.__dataclass_fields__
        }
    )

    from app.ml.state_detector import compute_state_inputs, detect_state

    state_inputs = compute_state_inputs(df_m15).reindex(features.index)

    from app.ml.regime_engine import _trend_of

    scored = 0
    engine: EngineState | None = None
    _backfill_run_dir: str | None = None
    _backfill_run_len = 0
    for ts in missing:
        pos = warm_index.get_loc(ts)
        if not isinstance(pos, (int, np.integer)):
            pos = int(np.where(warm_index == ts)[0][0])

        # Restore hysteresis from the immediately preceding BAR of this bar.
        prev_pred = (
            db.query(ModelPrediction)
            .filter(
                ModelPrediction.model_version_id == hmm_version.id,
                ModelPrediction.symbol == symbol,
                ModelPrediction.timeframe == "M15",
                ModelPrediction.ts < ts,
            )
            .order_by(ModelPrediction.ts.desc())
            .first()
        )
        engine = EngineState(engine_params)
        if prev_pred and (prev_pred.components_json or {}).get("engine_state"):
            engine.restore(prev_pred.components_json["engine_state"])

        posterior_row = posterior[pos]
        hmm_semantic = semantic_probabilities(posterior_row, mapping)
        rf_probs_dict = {
            str(c): float(rf_probs_all[pos][i])
            for i, c in enumerate(rf_model.classes_)
        }
        combined = combine_scores(hmm_semantic, rf_probs_dict, engine_params.weight_hmm)

        state_name = None
        state_strength = 0.0
        state_reason = None
        if ts in state_inputs.index:
            si = state_inputs.loc[ts]
            state_name, state_strength, state_reason = detect_state(
                si["displacement"], si["slope"], si["adx_norm"]
            )
            combined["state"] = state_name
            combined["state_strength"] = state_strength
            combined["state_displacement"] = float(si["displacement"])
        combined["h1_trend_context"] = float(features.loc[ts, "h1_trend_context"])
        combined["hour_utc"] = int(ts.hour)

        out = engine.step(combined)
        raw_regime = out["regime"]
        regime = out["regime"]

        # Backfilled bars must use the SAME causal short-trend filter as live,
        # otherwise the same candle is labelled one way here and another way on
        # the market page. The run length is derived from the raw engine output
        # seen so far — never from bars that come after this one.
        if engine_params.min_signal_bars > 1:
            d_now = _trend_of(regime)
            if d_now is None:
                _backfill_run_dir, _backfill_run_len = None, 0
            else:
                if d_now == _backfill_run_dir:
                    _backfill_run_len += 1
                else:
                    _backfill_run_dir, _backfill_run_len = d_now, 1
                if _backfill_run_len < engine_params.min_signal_bars:
                    regime = "SIDEWAYS"
                    out["reason_codes"] = list(out["reason_codes"]) + ["SHORT_TREND_COLLAPSED"]

        pred = ModelPrediction(
            model_version_id=hmm_version.id,
            symbol=symbol,
            timeframe="M15",
            ts=ts,
            regime=regime,
            confidence=out["confidence"],
            probabilities_json={
                "hmm_semantic": hmm_semantic,
                "rf": rf_probs_dict,
                "combined": {
                    k: round(float(v), 6)
                    for k, v in combined.items()
                    if isinstance(v, (int, float))
                },
            },
            components_json={
                "hmm_state": int(posterior_row.argmax()),
                "hmm_posterior": [round(float(p), 6) for p in posterior_row],
                "engine_state": out["engine_state"],
                "raw_regime": raw_regime,
                "model_versions": {"hmm": hmm_version.id, "rf": rf_version.id},
                "data_source": source,
                "detected_state": state_name,
                "detected_state_strength": round(state_strength, 4),
                "detected_state_reason": state_reason,
                "backfilled": True,
            },
            reason_codes_json=out["reason_codes"],
            permission=PERMISSIONS.get(regime, "NO_TRADE"),
            expiry_ts=ts + timedelta(seconds=2 * M15_PERIOD),
            data_timestamp=ts + timedelta(seconds=M15_PERIOD),
        )
        if _persist_prediction(db, pred, hmm_version, symbol, ts):
            scored += 1

    logger.info("Backfilled %d prediction(s) for %s (%d were missing)", scored, symbol, len(missing))
    return {"scored": scored, "missing": len(missing), "reason": "OK", "feature_version": feature_version}


def _compute_regime_payload(db: Session, symbol: str) -> dict:
    """Full inference payload; never raises (degraded -> UNKNOWN)."""
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


def _trade_ens_only_payload(db: Session, symbol: str) -> dict | None:
    """Explicit fallback when HMM/RF are archived and only trade_ens is live.

    This is NOT a market-regime prediction and is never mapped to TREND_UP /
    TREND_DOWN. It returns the trade_ens signal with its own regime badge and a
    clear reason code, so the UI does not show a misleading UNKNOWN.
    """
    from app.services.trade_signal import TradeSignalError, compute_latest_signal

    try:
        sig = compute_latest_signal(db)
    except TradeSignalError:
        return None
    except Exception:
        logger.exception("trade_ens fallback failed")
        return None
    return {
        "symbol": sig.get("symbol", symbol),
        "timeframe": sig.get("timeframe", "M15"),
        "timestamp": sig.get("bar_ts"),
        "regime": "TRADE_ENS",
        "engine": "trade_ens",
        "confidence": max(float(sig.get("p_long", 0.0)), float(sig.get("p_short", 0.0))),
        "probabilities": {"hmm_semantic": {}, "rf": {}},
        "model_version": sig.get("model_version_id"),
        "feature_version": sig.get("feature_version"),
        "data_timestamp": sig.get("bar_ts"),
        "data_source": sig.get("source"),
        "expiry": sig.get("expires_at"),
        "reason_codes": ["TRADE_ENS_ONLY"],
        "permission": "NO_TRADE",
        "data_age_minutes": round(float(sig.get("data_age_seconds", 0.0)) / 60.0, 1),
        "stale": bool(sig.get("stale")),
        "trade_ens": sig,
        "message": (
            "HMM/RF đã tắt; chỉ trade_ens đang hoạt động. Đây là tín hiệu "
            "LONG/SHORT/NO_TRADE, không phải market regime."
        ),
    }


# Short TTL cache: repeated polls (fast dashboard refresh) reuse the last
# inference. DB-level idempotency already guarantees one row per bar, so a
# short TTL only avoids repeated cheap DB lookups — it never delays a new bar.
_REGIME_CACHE: dict = {"key": None, "t": 0.0, "payload": None}
_REGIME_CACHE_TTL = 5.0


def regime_latest(db: Session, symbol: str = "XAUUSD") -> dict:
    """Public payload with a short TTL cache keyed on (source, latest M15 bar, model)."""
    import time as _time

    source = active_source(db, symbol, "M15")
    latest_ts = _latest_candle_ts(db, "M15", symbol, source)
    pair = get_active_approved_pair(db)
    hmm_version = pair[0] if pair else None
    rf_version = pair[1] if pair else None
    te_version = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == "trade_ens", ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
        if pair is None
        else None
    )
    engine_params_repr = json.dumps(
        (hmm_version.metrics_json or {}).get("engine_params", {}) if hmm_version else {},
        sort_keys=True,
        default=str,
    )
    key = (
        symbol,
        source,
        latest_ts.isoformat() if latest_ts else None,
        hmm_version.id if hmm_version else None,
        rf_version.id if rf_version else None,
        te_version.id if te_version else None,
        engine_params_repr,
    )
    now = _time.monotonic()
    if (
        _REGIME_CACHE["key"] == key
        and now - _REGIME_CACHE["t"] < _REGIME_CACHE_TTL
        and _REGIME_CACHE["payload"] is not None
    ):
        return {**_REGIME_CACHE["payload"], "cached": True}
    if pair is None and te_version is not None:
        payload = _trade_ens_only_payload(db, symbol)
        if payload is None:
            payload = _compute_regime_payload(db, symbol)
    else:
        payload = _compute_regime_payload(db, symbol)
    _REGIME_CACHE["key"] = key
    _REGIME_CACHE["t"] = now
    _REGIME_CACHE["payload"] = payload
    return payload
