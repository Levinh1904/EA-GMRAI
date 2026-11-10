"""Multi-timeframe feature engineering.

All features are computed at M15 bar close time t and use ONLY data <= t
(no lookahead). Formulas documented in docs/DATA_PIPELINE.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.indicators import adx, atr, efficiency_ratio, ema, log_return, sma

FEATURE_VERSION = "v1"

M15_FEATURES = [
    "ret1",
    "ret4",
    "atr_ratio",
    "ema_slope",
    "efficiency_ratio",
    "adx_norm",
    "di_gap",
]
H1_FEATURES = ["h1_ema_slope", "h1_atr_ratio", "h1_adx_norm", "h1_trend_context"]
M5_FEATURES = ["m5_ret_short", "m5_vol_ratio", "m5_momentum"]
ALL_FEATURES = M15_FEATURES + H1_FEATURES + M5_FEATURES

# Warmup bars needed before any feature row is valid (max rolling window)
MIN_BARS_M15 = 40
MIN_BARS_H1 = 40
MIN_BARS_M5 = 40


def _log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def compute_m15_features(df: pd.DataFrame) -> pd.DataFrame:
    """df: M15 candles indexed by bar open time (UTC), columns open/high/low/close."""
    out = pd.DataFrame(index=df.index)
    atr14 = atr(df, 14)
    atr_mean20 = sma(atr14, 20)
    ema20 = ema(df["close"], 20)
    adx14, plus_di, minus_di = adx(df, 14)

    out["ret1"] = log_return(df["close"], 1)
    out["ret4"] = log_return(df["close"], 4)
    out["atr_ratio"] = atr14 / atr_mean20
    out["ema_slope"] = (ema20 - ema20.shift(4)) / atr14
    out["efficiency_ratio"] = efficiency_ratio(df["close"], 10)
    out["adx_norm"] = adx14 / 100.0
    out["di_gap"] = (plus_di - minus_di) / 100.0
    return out


def compute_h1_features(df: pd.DataFrame) -> pd.DataFrame:
    atr14 = atr(df, 14)
    ema20 = ema(df["close"], 20)
    adx14, _, _ = adx(df, 14)
    out = pd.DataFrame(index=df.index)
    out["h1_ema_slope"] = (ema20 - ema20.shift(4)) / atr14
    out["h1_atr_ratio"] = atr14 / sma(atr14, 20)
    out["h1_adx_norm"] = adx14 / 100.0
    out["h1_trend_context"] = np.sign(df["close"] - ema20) * (adx14 / 100.0)
    return out


def compute_m5_features(df: pd.DataFrame) -> pd.DataFrame:
    rets = _log_returns(df["close"])
    atr14 = atr(df, 14)
    out = pd.DataFrame(index=df.index)
    out["m5_ret_short"] = log_return(df["close"], 6)
    out["m5_vol_ratio"] = rets.rolling(6).std() / rets.rolling(36).std()
    out["m5_momentum"] = (df["close"] - sma(df["close"], 12)) / atr14
    return out


def asof_closed(
    base: pd.DataFrame, other: pd.DataFrame, period_seconds: int, cols: list[str]
) -> pd.DataFrame:
    """Join `cols` of `other` onto `base` by the last bar of `other` whose
    close time (index + period) is <= each base timestamp (closed bars only)."""
    out = base.copy()
    if other is None or len(other) == 0:
        for c in cols:
            out[c] = np.nan
        return out

    other = other.copy()
    other["_close_time"] = other.index + pd.Timedelta(seconds=period_seconds)
    other = other[["_close_time"] + cols].sort_values("_close_time")

    base_times = pd.Series(base.index.values, index=base.index).sort_values()
    merged = pd.merge_asof(
        base_times.to_frame("_t"),
        other,
        left_on="_t",
        right_on="_close_time",
        direction="backward",
    )
    merged.index = base_times.index
    for c in cols:
        out[c] = merged[c].reindex(base.index)
    return out


def build_features(
    df_m5: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_h1: pd.DataFrame,
) -> pd.DataFrame:
    """Build the full feature matrix on M15 bar close times.

    All three timeframes are REQUIRED (multi-TF schema is fixed): if any of
    them is missing/insufficient, there are no valid feature rows and a
    ValueError is raised — callers must degrade to UNKNOWN, never fabricate.

    Returns DataFrame indexed by M15 bar open time, columns = ALL_FEATURES,
    rows with NaN (insufficient history) dropped.
    """
    for df, tf, min_bars in (
        (df_m5, "M5", MIN_BARS_M5),
        (df_m15, "M15", MIN_BARS_M15),
        (df_h1, "H1", MIN_BARS_H1),
    ):
        if df is None or len(df) < min_bars:
            raise ValueError(f"Insufficient {tf} candles: need >= {min_bars}, got {0 if df is None else len(df)}")

    m15 = compute_m15_features(df_m15)
    m15 = asof_closed(m15, compute_h1_features(df_h1), 3600, H1_FEATURES)
    m15 = asof_closed(m15, compute_m5_features(df_m5), 300, M5_FEATURES)

    out = m15[ALL_FEATURES]
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna()
    return out


def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """Convert candle dicts to DataFrame indexed by UTC open time."""
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    df = pd.DataFrame(candles)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df
