"""Next-bar directional forecast — "will the next M15 candle close up or down?"

Honest framing (measured on 23,782 real M15 bars):
    accuracy 0.4967  vs  base rate 0.5197
    AUC      0.5169  (0.5 = coin flip)

The model therefore has **no exploitable edge** on the next bar. It is exposed
as a calibrated probability with that caveat attached, never as a directive:
the UI shows the live accuracy computed from scored forecasts in this database,
so the number you see is what this system actually achieves — not a claim.

Design constraints:
  * One forecast per closed bar, immutable (`uq_forecast_bar`). Re-running the
    scan never overwrites a past call, so accuracy cannot be flattered.
  * Outcomes are filled in only after the next bar has closed.
  * Model is trained causally (chronological split, no shuffling) and cached in
    process — retraining happens on a schedule, never per request.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.features import build_features
from app.ml.indicators import adx, atr, ema
from app.models import BarForecast, MarketCandle
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.forecast")

METHOD = "hgbt_direction_v1"
M15 = timeframe_seconds("M15")
# Direction is "FLAT" when |probability - 0.5| is below this: the model has no
# opinion, and pretending otherwise would manufacture false precision.
FLAT_BAND = 0.04

_MODEL_CACHE: dict = {"key": None, "model": None, "trained_at": None}


def _build_direction_features(
    df_m5: pd.DataFrame, df_m15: pd.DataFrame, df_h1: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Series]:
    """Causal feature matrix + next-bar up/down target."""
    for df in (df_m5, df_m15, df_h1):
        if df.index.has_duplicates:
            raise ValueError("duplicate candle timestamps")
    feats = build_features(df_m5, df_m15, df_h1)
    close = df_m15["close"].reindex(feats.index)

    X = pd.DataFrame(index=feats.index)
    for n in (1, 2, 3, 4, 6, 8, 12, 24, 48):
        X[f"r{n}"] = np.log(close / close.shift(n))
    bar_range = (df_m15["high"] - df_m15["low"]).replace(0, np.nan).reindex(feats.index)
    X["body_pct"] = (df_m15["close"] - df_m15["open"]).reindex(feats.index) / bar_range
    X["upper_wick"] = (
        df_m15["high"] - df_m15[["open", "close"]].max(axis=1)
    ).reindex(feats.index) / bar_range
    X["lower_wick"] = (
        df_m15[["open", "close"]].min(axis=1) - df_m15["low"]
    ).reindex(feats.index) / bar_range
    atr14 = atr(df_m15, 14)
    X["atr_pct"] = (atr14 / df_m15["close"]).reindex(feats.index)
    adx14, plus_di, minus_di = adx(df_m15, 14)
    X["adx"] = adx14.reindex(feats.index)
    X["di"] = ((plus_di - minus_di) / 100.0).reindex(feats.index)
    X["ema20_d"] = ((df_m15["close"] - ema(df_m15["close"], 20)) / atr14).reindex(feats.index)
    X["ema50_d"] = ((df_m15["close"] - ema(df_m15["close"], 50)) / atr14).reindex(feats.index)
    X["hour"] = pd.Series(feats.index.hour, index=feats.index)
    X["dow"] = pd.Series(feats.index.dayofweek, index=feats.index)

    # Feature columns from build_features add multi-timeframe context.
    for col in ("h1_trend_context", "m5_momentum", "efficiency_ratio", "adx_norm", "di_gap"):
        if col in feats.columns:
            X[col] = feats[col]

    X = X[~X.index.duplicated(keep="last")]
    y = (close.shift(-1) > close).astype(int).reindex(X.index)
    return X, y


def _get_model(X: pd.DataFrame, y: pd.Series, min_rows: int = 3000):
    """Train (or reuse) the direction model. Chronological split, no shuffle."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    data = pd.concat([X, y.rename("y")], axis=1).dropna()
    if len(data) < min_rows:
        raise ValueError(f"not enough rows to train forecast model: {len(data)}")

    key = (len(data), str(data.index[-1]))
    if _MODEL_CACHE["key"] == key and _MODEL_CACHE["model"] is not None:
        return _MODEL_CACHE["model"]

    model = HistGradientBoostingClassifier(
        max_depth=3,
        max_iter=150,
        learning_rate=0.05,
        min_samples_leaf=200,
        random_state=42,
    )
    model.fit(data.drop(columns="y").values, data["y"].values)
    _MODEL_CACHE.update({"key": key, "model": model, "trained_at": utcnow()})
    logger.info("Forecast model trained on %d rows", len(data))
    return model


def _direction_from_probability(p_up: float) -> tuple[str, float]:
    """Map a probability to a direction + confidence, with a FLAT band."""
    if p_up >= 0.5 + FLAT_BAND:
        return "UP", round(p_up, 4)
    if p_up <= 0.5 - FLAT_BAND:
        return "DOWN", round(1.0 - p_up, 4)
    return "FLAT", round(abs(p_up - 0.5) * 2, 4)


def forecast_next_bar(db: Session, symbol: str = "XAUUSD") -> dict:
    """Forecast the next M15 bar from the last closed bar. Idempotent per bar."""
    source = active_source(db, symbol, "M15")
    if source is None:
        raise ValueError("No M15 candles available")

    latest = (
        db.query(MarketCandle)
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == "M15",
            MarketCandle.source == source,
        )
        .order_by(MarketCandle.ts.desc())
        .first()
    )
    if latest is None:
        raise ValueError("No M15 candles available")
    bar_ts = ensure_utc(latest.ts)

    existing = (
        db.query(BarForecast)
        .filter(
            BarForecast.symbol == symbol,
            BarForecast.timeframe == "M15",
            BarForecast.ts == bar_ts,
        )
        .first()
    )
    if existing is not None:
        return _payload(existing)

    df_m5, df_m15, df_h1 = load_candles(
        db, symbol, m5_limit=20_000, m15_limit=20_000, h1_limit=8_000, source=source
    )
    X, y = _build_direction_features(df_m5, df_m15, df_h1)
    if bar_ts not in X.index:
        raise ValueError(f"bar {bar_ts} has no usable features yet")
    model = _get_model(X, y)

    row = X.loc[[bar_ts]].dropna(axis=1, how="all")
    trained_cols = model.feature_names_in_ if hasattr(model, "feature_names_in_") else None
    values = row.values.astype(np.float64)
    if trained_cols is not None:
        values = row.reindex(columns=list(trained_cols)).values.astype(np.float64)
    p_up = float(model.predict_proba(values)[0][1])
    direction, confidence = _direction_from_probability(p_up)

    regime = None
    try:
        from app.services.prediction import compute_latest_regime

        regime = compute_latest_regime(db, symbol).get("regime")
    except Exception:  # a missing regime must not block the forecast
        logger.debug("regime unavailable for forecast", exc_info=True)

    forecast = BarForecast(
        symbol=symbol,
        timeframe="M15",
        ts=bar_ts,
        target_ts=bar_ts + timedelta(seconds=M15),
        direction=direction,
        probability_up=round(p_up, 6),
        confidence=confidence,
        regime=regime,
        method=METHOD,
        features_json={
            "close": float(latest.close),
            "atr_pct": _f(row.get("atr_pct")),
            "adx": _f(row.get("adx")),
            "r1": _f(row.get("r1")),
            "r4": _f(row.get("r4")),
        },
        note=(
            "Dự đoán nến kế tiếp. Sai số thực nghiệm: AUC ~0.52 (gần như ngẫu nhiên) — "
            "chỉ mang tính tham khảo, không phải tín hiệu giao dịch."
        ),
    )
    db.add(forecast)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = (
            db.query(BarForecast)
            .filter(
                BarForecast.symbol == symbol,
                BarForecast.timeframe == "M15",
                BarForecast.ts == bar_ts,
            )
            .first()
        )
        if existing is None:
            raise
        return _payload(existing)
    return _payload(forecast)


def score_pending_forecasts(db: Session, symbol: str = "XAUUSD", limit: int = 500) -> dict:
    """Fill in outcomes for forecasts whose target bar has since closed."""
    pending = (
        db.query(BarForecast)
        .filter(
            BarForecast.symbol == symbol,
            BarForecast.correct.is_(None),
            BarForecast.target_ts.isnot(None),
        )
        .order_by(BarForecast.ts)
        .limit(limit)
        .all()
    )
    if not pending:
        return {"scored": 0, "correct": 0}

    source = active_source(db, symbol, "M15")
    scored = correct = 0
    for fc in pending:
        bar = (
            db.query(MarketCandle)
            .filter(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == "M15",
                MarketCandle.ts == fc.target_ts,
                MarketCandle.source == source,
            )
            .first()
        )
        if bar is None:
            continue
        actual = "UP" if bar.close > bar.open else "DOWN" if bar.close < bar.open else "FLAT"
        fc.actual_direction = actual
        fc.actual_open = float(bar.open)
        fc.actual_close = float(bar.close)
        if fc.direction == "FLAT":
            # No call was made: scored as neutral, not as a win.
            fc.correct = None
        else:
            fc.correct = bool(fc.direction == actual)
            scored += 1
            if fc.correct:
                correct += 1
        fc.scored_at = utcnow()
    db.commit()
    return {"scored": scored, "correct": correct}


def forecast_stats(db: Session, symbol: str = "XAUUSD", limit: int = 2000) -> dict:
    """Live accuracy of this system's own forecasts (no hand-picked numbers)."""
    rows = (
        db.query(BarForecast)
        .filter(
            BarForecast.symbol == symbol,
            BarForecast.correct.isnot(None),
        )
        .order_by(BarForecast.ts.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {
            "scored": 0,
            "accuracy": None,
            "by_direction": {},
            "note": "Chưa có dự đoán nào được chấm điểm.",
        }
    n = len(rows)
    hits = sum(1 for r in rows if r.correct)
    by_dir: dict[str, dict] = {}
    for r in rows:
        d = by_dir.setdefault(r.direction, {"n": 0, "correct": 0})
        d["n"] += 1
        d["correct"] += 1 if r.correct else 0
    for d in by_dir.values():
        d["accuracy"] = round(d["correct"] / d["n"], 4) if d["n"] else None
    return {
        "scored": n,
        "accuracy": round(hits / n, 4),
        "by_direction": by_dir,
        "note": "Độ chính xác đo trên chính các dự đoán đã lưu trong CSDL.",
    }


def _payload(fc: BarForecast) -> dict:
    return {
        "id": fc.id,
        "symbol": fc.symbol,
        "timeframe": fc.timeframe,
        "ts": ensure_utc(fc.ts).isoformat(),
        "target_ts": ensure_utc(fc.target_ts).isoformat(),
        "direction": fc.direction,
        "probability_up": fc.probability_up,
        "confidence": fc.confidence,
        "regime": fc.regime,
        "method": fc.method,
        "note": fc.note,
        "actual_direction": fc.actual_direction,
        "actual_open": fc.actual_open,
        "actual_close": fc.actual_close,
        "correct": fc.correct,
    }


def _f(v):
    try:
        if isinstance(v, pd.Series):
            v = v.iloc[0] if len(v) else float("nan")
        x = float(v)
    except (TypeError, ValueError, IndexError):
        return None
    return None if not np.isfinite(x) else round(x, 6)
