"""Feature Schema v2 for the trade_ens model.

All M15 features are computed at bar close t from data <= t. H1/M5 context is
joined on the *close time* of the source bar (index + period), so a bar that is
not closed yet at t can never be used. See SPEC section 5.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features import (
    MIN_BARS_H1,
    MIN_BARS_M5,
    MIN_BARS_M15,
    asof_closed,
    candles_to_df,
    compute_h1_features,
    compute_m5_features,
)
from app.ml.indicators import adx, atr, efficiency_ratio, ema, log_return, rsi, sma

FEATURE_VERSION = "v2"

M15_BASE = [
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
M15_EXTENDED = [
    "plus_di_norm",
    "minus_di_norm",
    "ema_slope_slow",
    "ma_separation",
    "directional_persistence",
    "price_displacement",
    "rolling_directional_consistency",
    "atr_norm",
    "realized_vol",
    "vol_ratio",
    "vol_expansion",
    "roc_12",
    "rsi_norm",
    "momentum_accel",
    "price_velocity",
    "candle_body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "breakout_distance",
    "range_compression",
    "range_expansion",
]
TIME_FEATURES = ["hour_sin", "hour_cos"]
ALL_FEATURES = M15_BASE + H1_FEATURES + M5_FEATURES + M15_EXTENDED + TIME_FEATURES

assert len(ALL_FEATURES) == 37, f"Schema v2 must have 37 features, got {len(ALL_FEATURES)}"


def compute_m15_base(df: pd.DataFrame) -> pd.DataFrame:
    """Seven M15 features from SPEC 5.1."""
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


def compute_m15_extended(df: pd.DataFrame) -> pd.DataFrame:
    """Twenty-one extended M15 features from SPEC 5.3 (all causal)."""
    out = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    atr14 = atr(df, 14)
    adx14, plus_di, minus_di = adx(df, 14)
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    rets = log_return(close, 1)

    out["plus_di_norm"] = plus_di / 100.0
    out["minus_di_norm"] = minus_di / 100.0
    out["ema_slope_slow"] = (ema50 - ema50.shift(8)) / (2.0 * atr14)
    out["ma_separation"] = (ema20 - ema50) / atr14

    persistence = np.sign(close.diff()).rolling(10).mean()
    out["directional_persistence"] = persistence
    out["price_displacement"] = (close - close.shift(12)) / (atr14 * np.sqrt(12.0))
    out["rolling_directional_consistency"] = 0.5 * (
        1.0 + np.sign(close - close.shift(10)) * persistence
    )

    out["atr_norm"] = atr14 / close * 100.0
    out["realized_vol"] = rets.rolling(12).std() * 100.0
    out["vol_ratio"] = rets.rolling(6).std() / rets.rolling(24).std()
    out["vol_expansion"] = (atr14 - atr14.shift(4)) / atr14
    out["roc_12"] = log_return(close, 12)
    out["rsi_norm"] = (rsi(close, 14) - 50.0) / 50.0
    out["momentum_accel"] = ((close - close.shift(4)) - (close.shift(4) - close.shift(8))) / atr14
    out["price_velocity"] = (close - close.shift(4)) / (4.0 * atr14)

    span = (high - low).replace(0, np.nan)
    body = (close - open_).abs() / span
    upper = (high - pd.concat([open_, close], axis=1).max(axis=1)) / span
    lower = (pd.concat([open_, close], axis=1).min(axis=1) - low) / span
    out["candle_body_ratio"] = body.clip(lower=0.0, upper=1.0)
    out["upper_wick_ratio"] = upper.clip(lower=0.0, upper=1.0)
    out["lower_wick_ratio"] = lower.clip(lower=0.0, upper=1.0)

    high20 = high.rolling(20).max()
    low20 = low.rolling(20).min()
    mid20 = (high20 + low20) / 2.0
    out["breakout_distance"] = (close - mid20) / atr14

    range6 = (high.rolling(6).max() - low.rolling(6).min()).replace(0, np.nan)
    range20 = (high.rolling(20).max() - low.rolling(20).min()).replace(0, np.nan)
    out["range_compression"] = (range6 / range20).clip(lower=0.0, upper=2.0)
    out["range_expansion"] = ((high - low) / atr14).clip(lower=0.0, upper=10.0)
    return out


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """UTC hour-of-day cyclic features (no timezone ambiguity)."""
    out = pd.DataFrame(index=df.index)
    hour = df.index.hour.astype(float)
    out["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    return out


def build_features_v2(
    df_m5: pd.DataFrame,
    df_m15: pd.DataFrame,
    df_h1: pd.DataFrame,
) -> pd.DataFrame:
    """Build the exact 37-column Schema v2 matrix indexed by M15 open time."""
    for df, tf, min_bars in (
        (df_m5, "M5", MIN_BARS_M5),
        (df_m15, "M15", MIN_BARS_M15),
        (df_h1, "H1", MIN_BARS_H1),
    ):
        if df is None or len(df) < min_bars:
            raise ValueError(
                f"Insufficient {tf} candles: need >= {min_bars}, got {0 if df is None else len(df)}"
            )

    m15 = compute_m15_base(df_m15)
    extended = compute_m15_extended(df_m15)
    m15 = pd.concat([m15, extended], axis=1)
    m15 = asof_closed(m15, compute_h1_features(df_h1), 3600, H1_FEATURES)
    m15 = asof_closed(m15, compute_m5_features(df_m5), 300, M5_FEATURES)
    time_features = add_time_features(m15)
    out = pd.concat([m15, time_features], axis=1)[ALL_FEATURES]
    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    return out


__all__ = [
    "ALL_FEATURES",
    "FEATURE_VERSION",
    "H1_FEATURES",
    "M15_BASE",
    "M15_EXTENDED",
    "M5_FEATURES",
    "TIME_FEATURES",
    "add_time_features",
    "build_features_v2",
    "candles_to_df",
    "compute_m15_base",
    "compute_m15_extended",
]
