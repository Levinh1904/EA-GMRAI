"""Historical Regime Inference Engine.

Runs the approved GMRAI models over the ENTIRE candle history to produce a
causal per-bar operational regime. Reuses the exact runtime stack:
  - HmmFilter (forward-only, filtered posterior — NO smoothing, no lookahead)
  - Random Forest (posterior/transition features + market features)
  - Operational Regime Engine (thresholds/hysteresis persisted in model metrics)

The per-bar regime at time t depends ONLY on data <= t (truncation-invariance
is tested). Segments are consecutive runs of the same regime, split at regime
changes and at data gaps (never merged across missing data).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from app.ml.features import ALL_FEATURES, M15_FEATURES, build_features
from app.ml.hmm_model import hmm_filter_from_artifact
from app.ml.regime_engine import PERMISSIONS, EngineParams, EngineState, combine_scores
from app.ml.rf_model import RF_FEATURE_NAMES, build_rf_features, predict_proba_rf, semantic_probs_array

N_M15 = len(M15_FEATURES)


@dataclass
class HistoryConfig:
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    gap_split_multiple: float = 1.5  # split a segment when spacing > 1.5x the bar period
    touch_tolerance: float = 0.1  # sideways touch band = 10% of range width

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "gap_split_multiple": self.gap_split_multiple,
            "touch_tolerance": self.touch_tolerance,
        }


def run_historical_inference(
    df_m5: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_h1: pd.DataFrame,
    hmm_artifact: dict,
    rf_model,
    engine_params: dict,
) -> pd.DataFrame:
    """Causal per-bar operational regime over full history.

    Returns DataFrame indexed by M15 bar open time with columns:
    regime, confidence, permission, hmm_state, hmm_posterior, rf_probs,
    reason_codes, open/high/low/close, atr_ratio, adx_norm,
    efficiency_ratio, h1_trend_context, m5_momentum.
    """
    features = build_features(df_m5, df_m15, df_h1)
    if len(features) < 60:
        raise ValueError(f"Insufficient features for history run: {len(features)} rows")

    hmm_cols = hmm_artifact["feature_columns"]
    scaler_mean = np.array(hmm_artifact["scaler_mean"])
    scaler_std = np.array(hmm_artifact["scaler_std"])
    X_hmm = (features[hmm_cols].values.astype(np.float64) - scaler_mean) / np.maximum(scaler_std, 1e-9)

    hmm_filter = hmm_filter_from_artifact(hmm_artifact)
    posterior = hmm_filter.posterior(X_hmm)  # filtered, causal
    mapping = hmm_artifact["state_mapping"]
    transmat = np.array(hmm_artifact["params"]["transmat"])
    semantic_df = semantic_probs_array(posterior, mapping)
    rf_X = build_rf_features(posterior, transmat, mapping, features, semantic_df)[RF_FEATURE_NAMES]
    rf_probs = predict_proba_rf(rf_model, rf_X)

    params = EngineParams(
        **{k: v for k, v in engine_params.items() if k in EngineParams.__dataclass_fields__}
    )
    engine = EngineState(params)

    rows: list[dict] = []
    for i, ts in enumerate(features.index):
        hmm_sem = {c: float(semantic_df.iloc[i][c]) for c in semantic_df.columns}
        rf_p = {c: float(rf_probs.iloc[i][c]) for c in rf_probs.columns}
        combined = combine_scores(hmm_sem, rf_p, params.weight_hmm)
        out = engine.step(combined)
        rows.append(
            {
                "ts": ts,
                "regime": out["regime"],
                "confidence": out["confidence"],
                "permission": PERMISSIONS.get(out["regime"], "NO_TRADE"),
                "hmm_state": int(posterior[i].argmax()),
                "hmm_posterior": [round(float(p), 6) for p in posterior[i]],
                "rf_probs": {k: round(float(v), 6) for k, v in rf_p.items()},
                "reason_codes": out["reason_codes"],
                "atr_ratio": float(features["atr_ratio"].iloc[i]),
                "adx_norm": float(features["adx_norm"].iloc[i]),
                "efficiency_ratio": float(features["efficiency_ratio"].iloc[i]),
                "h1_trend_context": float(features["h1_trend_context"].iloc[i]),
                "m5_momentum": float(features["m5_momentum"].iloc[i]),
            }
        )
    bars = pd.DataFrame(rows).set_index("ts")

    # join OHLC from candles (bar open time == candle open time)
    for col in ("open", "high", "low", "close"):
        bars[col] = df_m15[col].reindex(bars.index).values
    bars = bars[bars["close"].notna()]
    return bars


def build_segments(
    bars: pd.DataFrame,
    period_seconds: int,
    gap_split_multiple: float = 1.5,
    touch_tolerance: float = 0.1,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    model_version_id: int | None = None,
) -> list[dict]:
    """Split per-bar regimes into segments with full statistics.

    A segment ends when the regime changes OR when consecutive bars are
    further apart than gap_split_multiple * period (missing data splits the
    segment — information about the gap is preserved, never merged away).
    """
    if len(bars) == 0:
        return []

    period = timedelta(seconds=period_seconds)
    segments: list[dict] = []
    idxs = list(bars.index)
    start_i = 0
    current_regime = bars["regime"].iloc[0]
    split_reason = None

    def _segment(si: int, ei: int, reason: str | None) -> dict:
        sub = bars.iloc[si : ei + 1]
        n = len(sub)
        start_px = float(sub["open"].iloc[0])
        end_px = float(sub["close"].iloc[-1])
        high_px = float(sub["high"].max())
        low_px = float(sub["low"].min())
        net = end_px - start_px
        if net >= 0:
            mfe, mae = high_px - start_px, start_px - low_px
        else:
            mfe, mae = start_px - low_px, high_px - start_px
        # sideways range touches (band = touch_tolerance * range width)
        width = max(high_px - low_px, 1e-9)
        band = width * touch_tolerance
        touches_high = int((sub["high"] >= high_px - band).sum())
        touches_low = int((sub["low"] <= low_px + band).sum())
        # mean semantic posterior over the segment
        post_mean: dict[str, float] = {}
        if "hmm_posterior" in sub.columns:
            arr = np.vstack(sub["hmm_posterior"].values)
            for k in range(arr.shape[1]):
                post_mean[str(k)] = round(float(arr[:, k].mean()), 6)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "segment_index": len(segments) + 1,
            "regime": str(current_regime),
            "start_ts": idxs[si],
            "end_ts": idxs[ei],
            "bar_count": n,
            "duration_minutes": int(n * period_seconds / 60),
            "start_price": round(start_px, 3),
            "end_price": round(end_px, 3),
            "high_price": round(high_px, 3),
            "low_price": round(low_px, 3),
            "net_change": round(net, 3),
            "mfe": round(mfe, 3),
            "mae": round(mae, 3),
            "atr_mean": round(float(sub["atr_ratio"].mean()), 6),
            "adx_mean": round(float(sub["adx_norm"].mean()), 6),
            "efficiency_mean": round(float(sub["efficiency_ratio"].mean()), 6),
            "hmm_probs_json": post_mean,
            "confidence_mean": round(float(sub["confidence"].mean()), 4),
            "model_version_id": model_version_id,
            "split_reason": reason,
            "range_touches_high": touches_high,
            "range_touches_low": touches_low,
        }

    for i in range(1, len(bars)):
        reg = bars["regime"].iloc[i]
        gap = idxs[i] - idxs[i - 1]
        regime_changed = reg != current_regime
        data_gap = gap > period * gap_split_multiple
        if regime_changed or data_gap:
            segments.append(_segment(start_i, i - 1, "data_gap" if data_gap else None))
            start_i = i
            current_regime = reg
    segments.append(_segment(start_i, len(bars) - 1, None))  # end-of-data segment
    return segments
