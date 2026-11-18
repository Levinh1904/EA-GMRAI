"""Current market state detection — directional evidence from closed bars only.

Why this exists
---------------
The supervised models label every bar with its FUTURE move (``close[t+h] -
close[t]``) and are then applied live. That construction is inherently lagging:
a bar only becomes a "trend" label once the move has already happened, and the
hysteresis layer adds further delay on top. Measured on 23k real M15 bars, the
resulting signal arrived a median of ~28 bars (7h) after the move began and
missed roughly half of all trend windows.

This module answers a different — and answerable — question: *what is the
market doing right now?* It reads only information available at bar close:

    displacement = (close[t] - close[t-12]) / (2 * ATR14[t])
    slope        = (EMA20[t] - EMA20[t-4]) / ATR14[t]
    adx          = ADX14[t] / 100

Measured against same-time labels this reaches macro-F1 ~0.845 and fires 2-4
bars BEFORE a >1% move completes, versus ~18-25 bars late for the predictive
path. It is deliberately a *detector*, not a forecaster: it cannot tell you
what happens next, only what is happening now.

Never looks ahead: every input is computed from bars up to and including t.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.indicators import adx, atr, ema


@dataclass
class StateDetectorConfig:
    disp_bars: int = 12          # lookback for displacement (12 M15 = 3h)
    disp_atr_scale: float = 2.0  # displacement measured in this many ATRs
    slope_bars: int = 4          # EMA slope lookback

    # A trend must clear BOTH a displacement gate and an ADX gate; a very large
    # displacement can stand alone (fast impulse), but never without slope
    # agreement.
    disp_trend: float = 0.40     # |displacement| needed with ADX support
    disp_impulse: float = 1.00   # |displacement| that stands on its own
    slope_trend: float = 0.25    # |slope| needed with ADX support
    adx_trend: float = 0.22      # ADX/100 needed with displacement support

    # ---- Signal-quality gate ------------------------------------------------
    # Measured on 1,319 real M15 trend segments: segments where the signal
    # fired with |displacement| < 0.9 reversed 40% of the time before the
    # segment ended, while |displacement| >= 1.2 reversed only ~27%. Requiring
    # H1 agreement on top raises the out-of-sample win rate to ~77%.
    # `min_disp_signal` = 0 disables the gate (report every detected trend).
    min_disp_signal: float = 0.0
    require_h1_agreement: bool = False

    def to_dict(self) -> dict:
        return {
            "disp_bars": self.disp_bars,
            "disp_atr_scale": self.disp_atr_scale,
            "slope_bars": self.slope_bars,
            "disp_trend": self.disp_trend,
            "disp_impulse": self.disp_impulse,
            "slope_trend": self.slope_trend,
            "adx_trend": self.adx_trend,
            "min_disp_signal": self.min_disp_signal,
            "require_h1_agreement": self.require_h1_agreement,
        }


def compute_state_inputs(
    df_m15: pd.DataFrame, cfg: StateDetectorConfig | None = None
) -> pd.DataFrame:
    """Causal per-bar inputs for state detection (no lookahead)."""
    cfg = cfg or StateDetectorConfig()
    close = df_m15["close"]
    atr14 = atr(df_m15, 14).replace(0, np.nan)
    ema20 = ema(close, 20)
    adx14, plus_di, minus_di = adx(df_m15, 14)

    out = pd.DataFrame(index=df_m15.index)
    out["displacement"] = (close - close.shift(cfg.disp_bars)) / (
        cfg.disp_atr_scale * atr14
    )
    out["slope"] = (ema20 - ema20.shift(cfg.slope_bars)) / atr14
    out["adx_norm"] = adx14 / 100.0
    out["di_gap"] = (plus_di - minus_di) / 100.0
    return out


def detect_state(
    displacement: float | None,
    slope: float | None,
    adx_norm: float | None,
    cfg: StateDetectorConfig | None = None,
) -> tuple[str, float, str]:
    """Classify the CURRENT bar as TREND_UP / TREND_DOWN / SIDEWAYS.

    Returns ``(state, strength, reason)`` where ``strength`` is a 0..1 measure
    of how clearly directional the evidence is (0 for SIDEWAYS).

    A direction needs slope agreement plus either ADX support with moderate
    displacement, or a large displacement impulse. Missing inputs degrade to
    SIDEWAYS — never a fabricated trend.
    """
    cfg = cfg or StateDetectorConfig()
    if displacement is None or slope is None or adx_norm is None:
        return "SIDEWAYS", 0.0, "insufficient_input"
    try:
        d = float(displacement)
        s = float(slope)
        a = float(adx_norm)
    except (TypeError, ValueError):
        return "SIDEWAYS", 0.0, "insufficient_input"
    if not (np.isfinite(d) and np.isfinite(s) and np.isfinite(a)):
        return "SIDEWAYS", 0.0, "insufficient_input"

    # Directional agreement: displacement and slope must point the same way.
    for direction, sign in (("TREND_UP", 1.0), ("TREND_DOWN", -1.0)):
        dd, ss = d * sign, s * sign
        if dd <= 0 or ss <= 0:
            continue
        with_adx = (
            dd >= cfg.disp_trend and ss >= cfg.slope_trend and a >= cfg.adx_trend
        )
        as_impulse = dd >= cfg.disp_impulse and ss >= cfg.slope_trend
        if with_adx or as_impulse:
            # Strength blends how far past each gate we are (0..1).
            strength = float(
                np.mean(
                    [
                        min(dd / max(cfg.disp_impulse, 1e-9), 1.0),
                        min(ss / max(cfg.slope_trend * 3.0, 1e-9), 1.0),
                        min(a / max(cfg.adx_trend * 3.0, 1e-9), 1.0),
                    ]
                )
            )
            reason = "impulse" if (as_impulse and not with_adx) else "adx_displacement"
            return direction, round(strength, 4), reason
    return "SIDEWAYS", 0.0, "no_directional_evidence"


def detect_state_series(
    df_m15: pd.DataFrame, cfg: StateDetectorConfig | None = None
) -> pd.DataFrame:
    """Per-bar state detection over a whole M15 frame (causal, vectorised)."""
    cfg = cfg or StateDetectorConfig()
    inputs = compute_state_inputs(df_m15, cfg).dropna()
    rows = []
    for ts, r in inputs.iterrows():
        state, strength, reason = detect_state(
            r["displacement"], r["slope"], r["adx_norm"], cfg
        )
        rows.append({"ts": ts, "state": state, "strength": strength, "reason": reason})
    if not rows:
        return pd.DataFrame(columns=["state", "strength", "reason"]).set_index(
            pd.Index([], name="ts")
        )
    return pd.DataFrame(rows).set_index("ts")


def signal_quality(
    displacement: float | None,
    h1_trend_context: float | None,
    direction: str,
    cfg: StateDetectorConfig | None = None,
) -> tuple[bool, str]:
    """Should a detected trend be published as a signal?

    Motivation (measured, not assumed): publishing every detected trend gave a
    61.9% out-of-sample win rate, and segments shorter than 8 bars reversed
    72% of the time. Filtering for ``|displacement| >= 1.2`` with H1 agreement
    raised that to 77.4% while keeping ~15% of signals.

    Returns ``(ok, reason)``. ``reason`` explains a rejection so the UI can say
    why nothing was published instead of silently showing SIDEWAYS.
    """
    cfg = cfg or StateDetectorConfig()
    if cfg.min_disp_signal <= 0 and not cfg.require_h1_agreement:
        return True, "gate_disabled"

    try:
        d = abs(float(displacement)) if displacement is not None else float("nan")
    except (TypeError, ValueError):
        d = float("nan")
    if not np.isfinite(d):
        return False, "no_displacement"

    if d < cfg.min_disp_signal:
        return False, f"weak_displacement_{d:.2f}"

    if cfg.require_h1_agreement:
        if h1_trend_context is None or not np.isfinite(float(h1_trend_context)):
            return False, "no_h1_context"
        h1 = float(h1_trend_context)
        want = 1.0 if direction == "TREND_UP" else -1.0
        if np.sign(h1) != want:
            return False, "h1_disagrees"

    return True, "ok"
