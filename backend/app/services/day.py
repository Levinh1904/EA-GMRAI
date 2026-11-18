"""Day-scoped regime analysis — "what happened on a given day".

Answers a single, common research question without creating a full history run:
for one UTC day, replay the approved models causally over that day's M15 bars
and return per-bar AI regime, the independent reference regime, OHLC and
segment-level statistics.

Causality: inference always uses history UP TO the end of the requested day,
never beyond, so inspecting yesterday can never peek at today's bars. Features
need warm-up, so candles are loaded from well before the day starts.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ml.history import build_segments, run_historical_inference
from app.ml.hmm_model import load_hmm_artifact
from app.models import MarketCandle, ModelVersion
from app.services.source import active_source
from app.services.training import load_candles
from app.timeutil import ensure_utc, timeframe_seconds, utcnow

logger = logging.getLogger("gmrai.day")

# Warm-up: features need ~40 M15 bars, HMM needs a longer window for a stable
# filtered posterior. 3 days of padding covers weekends/holidays cheaply.
WARMUP_PAD_DAYS = 3


class DayAnalysisError(RuntimeError):
    pass


def _approved(db: Session, model_type: str) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == model_type, ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )


def _resolve_day(day: str | None) -> datetime:
    """Parse YYYY-MM-DD (UTC). Default = yesterday (UTC)."""
    if not day:
        return (utcnow() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
    except ValueError as e:
        raise DayAnalysisError(f"Invalid date {day!r}, expected YYYY-MM-DD") from e
    return d.replace(tzinfo=timezone.utc)


def analyze_day(db: Session, day: str | None = None, symbol: str = "XAUUSD") -> dict:
    start = _resolve_day(day)
    end = start + timedelta(days=1)

    source = active_source(db, symbol, "M15")
    if source is None:
        raise DayAnalysisError("No M15 candles available")

    hmm_version = _approved(db, "hmm")
    rf_version = _approved(db, "random_forest")
    if hmm_version is None or rf_version is None:
        raise DayAnalysisError("No approved model pair — train and approve a model first")
    if not hmm_version.artifact_path or not rf_version.artifact_path:
        raise DayAnalysisError("Approved model artifacts missing on disk")

    # Real coverage of the requested day (for an honest "no data" answer).
    day_count = (
        db.query(func.count(MarketCandle.id))
        .filter(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == "M15",
            MarketCandle.source == source,
            MarketCandle.ts >= start,
            MarketCandle.ts < end,
        )
        .scalar()
    ) or 0
    if day_count == 0:
        return {
            "symbol": symbol,
            "day": start.date().isoformat(),
            "data_source": source,
            "bar_count": 0,
            "bars": [],
            "segments": [],
            "summary": {},
            "reason": "NO_DATA_FOR_DAY",
            "note": "Không có nến M15 cho ngày này (thị trường đóng cửa hoặc chưa thu thập).",
        }

    hmm_artifact = load_hmm_artifact(Path(hmm_version.artifact_path))
    rf_model = joblib.load(Path(rf_version.artifact_path))
    engine_params = (hmm_version.metrics_json or {}).get("engine_params") or {}
    if not engine_params:
        raise DayAnalysisError("HMM version has no engine_params in metrics")

    # Load history up to the END of the requested day only (strict cutoff —
    # never let data after the day influence its analysis).
    pad_start = start - timedelta(days=WARMUP_PAD_DAYS)
    pad_days = (end - pad_start).days

    def fetch(tf: str) -> pd.DataFrame:
        rows = (
            db.query(MarketCandle)
            .filter(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == tf,
                MarketCandle.source == source,
                MarketCandle.ts >= pad_start,
                MarketCandle.ts < end,
            )
            .order_by(MarketCandle.ts)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.DataFrame(
            [
                {
                    "ts": ensure_utc(r.ts),
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "tick_volume": r.tick_volume,
                    "spread": r.spread,
                }
                for r in rows
            ]
        )
        return df.set_index("ts").sort_index()

    df_m5, df_m15, df_h1 = fetch("M5"), fetch("M15"), fetch("H1")
    if len(df_m5) < 40 or len(df_m15) < 60 or len(df_h1) < 40:
        raise DayAnalysisError(
            f"Insufficient candles around {start.date()} "
            f"(M5={len(df_m5)}, M15={len(df_m15)}, H1={len(df_h1)}); need >=40 M15/H1 and >=40 M5"
        )

    bars = run_historical_inference(df_m5, df_m15, df_h1, hmm_artifact, rf_model, engine_params)

    # Independent rule-based reference regime (closed candles only).
    from app.ml.reference_engine import ReferenceConfig, classify_reference

    ref_cfg = ReferenceConfig()
    reference = classify_reference(df_m15, ref_cfg)

    day_bars = bars[(bars.index >= start) & (bars.index < end)]
    if len(day_bars) == 0:
        raise DayAnalysisError(f"No inferred bars in {start.date()}")

    segments = build_segments(
        day_bars,
        timeframe_seconds("M15"),
        symbol=symbol,
        timeframe="M15",
        model_version_id=hmm_version.id,
    )

    out_bars = []
    for ts, row in day_bars.iterrows():
        ref_row = reference.loc[ts] if ts in reference.index else None
        out_bars.append(
            {
                "ts": ensure_utc(ts).isoformat(),
                "regime": str(row["regime"]),
                "confidence": round(float(row["confidence"]), 4),
                "permission": str(row["permission"]),
                "reference_regime": str(ref_row["regime"]) if ref_row is not None else None,
                "reference_reason": str(ref_row["reason"]) if ref_row is not None else None,
                "hmm_state": int(row["hmm_state"]),
                "hmm_posterior": [round(float(p), 6) for p in row["hmm_posterior"]],
                "rf_probs": {k: round(float(v), 6) for k, v in row["rf_probs"].items()},
                "reason_codes": list(row["reason_codes"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "atr_ratio": _f(row.get("atr_ratio")),
                "adx_norm": _f(row.get("adx_norm")),
                "efficiency_ratio": _f(row.get("efficiency_ratio")),
                "h1_trend_context": _f(row.get("h1_trend_context")),
                "m5_momentum": _f(row.get("m5_momentum")),
            }
        )

    first, last = day_bars.iloc[0], day_bars.iloc[-1]
    high = float(day_bars["high"].max())
    low = float(day_bars["low"].min())
    open_px, close_px = float(first["open"]), float(last["close"])
    regime_share: dict[str, int] = {}
    for b in out_bars:
        regime_share[b["regime"]] = regime_share.get(b["regime"], 0) + 1
    ref_share: dict[str, int] = {}
    for b in out_bars:
        key = b["reference_regime"] or "UNKNOWN"
        ref_share[key] = ref_share.get(key, 0) + 1

    # Direction accuracy + wrong-call breakdown for THIS day. Same definitions
    # as the full-history tabs so the numbers are comparable across scopes.
    from app.ml.history_stats import direction_accuracy, wrong_direction_analysis

    accuracy = direction_accuracy(segments, day_bars)
    wrong = wrong_direction_analysis(segments, day_bars)

    # A single day yields only a handful of trend segments, so a 100% or 0%
    # accuracy is noise, not skill. Say so in the payload instead of letting
    # the UI imply statistical meaning that isn't there.
    n_segments = accuracy.get("per_segment", {}).get("overall", {}).get("total") or 0
    reliability = (
        "insufficient"
        if n_segments < 5
        else "low"
        if n_segments < 15
        else "moderate"
        if n_segments < 40
        else "ok"
    )
    accuracy["sample"] = {
        "segments": n_segments,
        "reliability": reliability,
        "note": (
            "Một ngày chỉ có vài đoạn xu hướng — tỷ lệ trên mẫu nhỏ không đủ "
            "kết luận. Dùng tab 'Độ chính xác hướng' của cả năm để đánh giá thật."
            if reliability in ("insufficient", "low")
            else "Mẫu trong ngày; vẫn nên đối chiếu với thống kê cả năm."
        ),
    }

    return {
        "symbol": symbol,
        "day": start.date().isoformat(),
        "data_source": source,
        "bar_count": len(out_bars),
        "open": round(open_px, 3),
        "close": round(close_px, 3),
        "high": round(high, 3),
        "low": round(low, 3),
        "net_change": round(close_px - open_px, 3),
        "net_change_pct": round((close_px - open_px) / open_px * 100, 3) if open_px else None,
        "range": round(high - low, 3),
        "model_versions": {"hmm": hmm_version.id, "rf": rf_version.id},
        "summary": {
            "regime_bars": regime_share,
            "reference_bars": ref_share,
            "segment_count": len(segments),
            "first_bar": out_bars[0]["ts"],
            "last_bar": out_bars[-1]["ts"],
        },
        "direction_accuracy": accuracy,
        "wrong_direction": wrong,
        "segments": [
            {
                "segment_index": s["segment_index"],
                "regime": s["regime"],
                "start_ts": ensure_utc(s["start_ts"]).isoformat(),
                "end_ts": ensure_utc(s["end_ts"]).isoformat(),
                "bar_count": s["bar_count"],
                "duration_minutes": s["duration_minutes"],
                "start_price": s["start_price"],
                "end_price": s["end_price"],
                "net_change": s["net_change"],
                "mfe": s["mfe"],
                "mae": s["mae"],
            }
            for s in segments
        ],
        "bars": out_bars,
        "note": (
            "Phân tích nhân quả: chỉ dùng nến có timestamp < cuối ngày được chọn. "
            "Nến M15 là nến đã đóng — không có dữ liệu trong tương lai."
        ),
    }


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else round(f, 6)
