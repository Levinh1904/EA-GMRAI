"""Random Forest supervised labels — future return as TRAINING TARGET only.

Labels are built from forward returns over `horizon` bars normalized by ATR
(known at time t). Forward data is used ONLY as a label; it never enters
features. Purge/embargo is handled by the split functions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.indicators import atr

LABEL_CLASSES = ["TREND_DOWN", "SIDEWAYS", "TREND_UP"]


def make_labels(
    close: pd.Series,
    atr_series: pd.Series | None = None,
    df: pd.DataFrame | None = None,
    horizon: int = 12,
    up_threshold_atr: float = 0.75,
) -> pd.Series:
    """Label each bar t using the forward PRICE MOVE over `horizon` bars
    relative to ATR14(t) (both in price units):

    move(t) = close[t+h] - close[t]
    move > +thr*ATR(t) -> TREND_UP; move < -thr*ATR(t) -> TREND_DOWN; else SIDEWAYS.

    Forward data is used ONLY as a label (training target); it never enters
    features. The last `horizon` bars get NaN (no valid future).
    """
    if atr_series is None:
        if df is None:
            raise ValueError("need atr_series or df")
        atr_series = atr(df, 14)
    fwd = close.shift(-horizon) - close
    thr = up_threshold_atr * atr_series
    labels = pd.Series("SIDEWAYS", index=close.index, dtype=object)
    labels[fwd > thr] = "TREND_UP"
    labels[fwd < -thr] = "TREND_DOWN"
    labels.iloc[-horizon:] = np.nan  # no valid future
    return labels


def label_counts(labels: pd.Series) -> dict:
    return labels.dropna().value_counts().to_dict()
