"""Independent Reference Regime Engine — quantitative RULE-BASED classifier.

Independence by construction: this module receives ONLY closed candles and
a versioned configuration. It never touches HMM states/posteriors, Random
Forest probabilities, or the AI Operational Regime outputs.

Thresholds are RESEARCH parameters (documented, configurable, versioned) —
they are NOT validated ground truth and are NEVER tuned to maximize
agreement with the AI models.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.ml.indicators import adx, atr, efficiency_ratio, ema

REFERENCE_LABELS = ["TREND_UP", "TREND_DOWN", "SIDEWAYS", "TRANSITION", "HIGH_VOLATILITY", "UNKNOWN"]


@dataclass(frozen=True)
class ReferenceConfig:
    # --- indicator parameters ---
    adx_period: int = 14
    ema_period: int = 20
    ema_slope_bars: int = 4
    channel_period: int = 20          # rolling high/low channel (Donchian)
    displacement_bars: int = 10       # net price displacement lookback
    min_history_bars: int = 60

    # --- classification thresholds (research parameters, configurable) ---
    vol_atr_ratio: float = 1.5        # HIGH_VOLATILITY when ATR ratio >= this
    trend_adx_min: float = 0.25       # trend requires ADX/100 >= this
    sideways_adx_max: float = 0.20    # sideways requires ADX/100 <= this
    trend_disp_min_atr: float = 0.30  # trend requires |displacement| >= N * ATR
    sideways_eff_max: float = 0.40    # sideways requires efficiency ratio <= this

    # --- versioning ---
    version: str = "ref_v1"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReferenceConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def compute_reference_indicators(df_m15: pd.DataFrame, cfg: ReferenceConfig) -> pd.DataFrame:
    """Independent indicators on CLOSED candles only (no model inputs)."""
    out = pd.DataFrame(index=df_m15.index)
    adx_raw, plus_di, minus_di = adx(df_m15, cfg.adx_period)
    atr_raw = atr(df_m15, cfg.adx_period)
    ema_line = ema(df_m15["close"], cfg.ema_period)

    out["adx_norm"] = adx_raw / 100.0
    out["di_gap"] = (plus_di - minus_di) / 100.0
    out["atr_ratio"] = atr_raw / atr_raw.rolling(20).mean()
    out["ema_slope"] = (ema_line - ema_line.shift(cfg.ema_slope_bars)) / atr_raw
    out["efficiency_ratio"] = efficiency_ratio(df_m15["close"], 10)
    out["channel_high"] = df_m15["high"].rolling(cfg.channel_period).max()
    out["channel_low"] = df_m15["low"].rolling(cfg.channel_period).min()
    out["displacement"] = (df_m15["close"] - df_m15["close"].shift(cfg.displacement_bars)) / atr_raw
    return out


def classify_reference(
    df_m15: pd.DataFrame, cfg: ReferenceConfig | None = None
) -> pd.DataFrame:
    """Rule-based classification of every closed M15 bar.

    Returns DataFrame indexed by bar open time with columns:
    regime, reason, and the indicator values used.
    Rule order (documented): UNKNOWN (insufficient history) → HIGH_VOLATILITY
    → TREND_UP/DOWN → SIDEWAYS → TRANSITION → UNKNOWN (ambiguous).
    """
    cfg = cfg or ReferenceConfig()
    ind = compute_reference_indicators(df_m15, cfg)
    out = pd.DataFrame(index=ind.index)

    regimes = np.full(len(ind), "UNKNOWN", dtype=object)
    reasons = np.full(len(ind), "", dtype=object)

    hist_ok = (
        ind["adx_norm"].notna()
        & ind["atr_ratio"].notna()
        & ind["channel_high"].notna()
        & ind["displacement"].notna()
    )
    reasons[~hist_ok] = "insufficient_history"

    for i in np.where(hist_ok)[0]:
        adx_n = ind["adx_norm"].iloc[i]
        di = ind["di_gap"].iloc[i]
        atr_r = ind["atr_ratio"].iloc[i]
        slope = ind["ema_slope"].iloc[i]
        eff = ind["efficiency_ratio"].iloc[i]
        disp = ind["displacement"].iloc[i]

        if atr_r >= cfg.vol_atr_ratio:
            regimes[i] = "HIGH_VOLATILITY"
            reasons[i] = f"atr_ratio>={cfg.vol_atr_ratio}"
        elif adx_n >= cfg.trend_adx_min and di > 0 and slope > 0 and disp >= cfg.trend_disp_min_atr:
            regimes[i] = "TREND_UP"
            reasons[i] = (
                f"adx>={cfg.trend_adx_min};di>0;slope>0;disp>={cfg.trend_disp_min_atr}ATR"
            )
        elif adx_n >= cfg.trend_adx_min and di < 0 and slope < 0 and disp <= -cfg.trend_disp_min_atr:
            regimes[i] = "TREND_DOWN"
            reasons[i] = (
                f"adx>={cfg.trend_adx_min};di<0;slope<0;disp<=-{cfg.trend_disp_min_atr}ATR"
            )
        elif adx_n <= cfg.sideways_adx_max and abs(disp) < cfg.trend_disp_min_atr and eff <= cfg.sideways_eff_max:
            regimes[i] = "SIDEWAYS"
            reasons[i] = (
                f"adx<={cfg.sideways_adx_max};|disp|<{cfg.trend_disp_min_atr}ATR;eff<={cfg.sideways_eff_max}"
            )
        elif cfg.sideways_adx_max < adx_n < cfg.trend_adx_min:
            regimes[i] = "TRANSITION"
            reasons[i] = f"adx_in({cfg.sideways_adx_max},{cfg.trend_adx_min})"
        else:
            regimes[i] = "UNKNOWN"
            reasons[i] = "ambiguous_mixed_signals"

    out["regime"] = regimes
    out["reason"] = reasons
    for col in ind.columns:
        out[col] = ind[col].values
    return out
