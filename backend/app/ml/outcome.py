"""Retrospective Future Outcome Evaluator.

For each prediction timestamp, evaluates what the price ACTUALLY did over
configurable future horizons. Future observations are used ONLY for
evaluation — they never alter the original AI prediction or the Reference
classification (both are stored before this runs).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from app.ml.indicators import atr

DEFAULT_HORIZONS = (12, 48, 96)  # M15 bars: 3h, 12h, 24h


@dataclass(frozen=True)
class OutcomeConfig:
    horizons: tuple[int, ...] = DEFAULT_HORIZONS
    range_atr_mult: float = 1.5   # "in range" band = ±mult*ATR from entry close
    direction_atr_mult: float = 0.5  # directional move threshold in ATR units

    def to_dict(self) -> dict:
        return {"horizons": list(self.horizons), "range_atr_mult": self.range_atr_mult,
                "direction_atr_mult": self.direction_atr_mult}


def _future_max(s: pd.Series, h: int) -> pd.Series:
    """Rolling max over the NEXT h values (index t -> max of t+1..t+h).

    Pure numpy (sliding window) — immune to pandas' freq-aware .shift()
    semantics on regular DatetimeIndexes."""
    vals = np.asarray(s, dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    if n > h:
        w = sliding_window_view(vals, h + 1)
        out[: n - h] = w[:, 1:].max(axis=1)
    return pd.Series(out, index=s.index)


def _future_min(s: pd.Series, h: int) -> pd.Series:
    vals = np.asarray(s, dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    if n > h:
        w = sliding_window_view(vals, h + 1)
        out[: n - h] = w[:, 1:].min(axis=1)
    return pd.Series(out, index=s.index)


def compute_outcomes(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    atr_series: pd.Series,
    cfg: OutcomeConfig | None = None,
) -> pd.DataFrame:
    """Per-timestamp future outcomes for each horizon (evaluation only).

    Columns per horizon h: fwd_return_{h}, mfe_{h}, mae_{h}, direction_{h},
    in_range_{h}. Rows with insufficient future data are dropped.
    """
    cfg = cfg or OutcomeConfig()
    frames = []
    for h in cfg.horizons:
        fwd = close.shift(-h) - close
        hi_fwd = _future_max(high, h)
        lo_fwd = _future_min(low, h)
        mfe = hi_fwd - close  # favorable excursion (up) from entry
        mae = close - lo_fwd  # adverse excursion (down) from entry
        thr = cfg.direction_atr_mult * atr_series
        direction = np.where(fwd > thr, "UP", np.where(fwd < -thr, "DOWN", "FLAT"))
        band = cfg.range_atr_mult * atr_series
        in_range = (hi_fwd - lo_fwd) <= band
        frames.append(
            pd.DataFrame(
                {
                    f"fwd_return_{h}": fwd,
                    f"mfe_{h}": mfe,
                    f"mae_{h}": mae,
                    f"direction_{h}": direction,
                    f"in_range_{h}": in_range,
                },
                index=close.index,
            )
        )
    out = pd.concat(frames, axis=1)
    return out.dropna()
