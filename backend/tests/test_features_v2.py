"""Schema v2: exact 37 columns and no future leakage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features_v2 import ALL_FEATURES, FEATURE_VERSION, build_features_v2


def _candles(n: int, freq: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq=freq, tz="UTC")
    rets = rng.normal(0, 0.0008, n)
    close = 2000.0 * np.exp(np.cumsum(rets))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.3, n))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": np.full(n, 100),
            "spread": np.full(n, 20.0),
        },
        index=idx,
    )


def test_schema_v2_has_exactly_37_causal_columns():
    m5 = _candles(3000, "5min", 1)
    m15 = _candles(900, "15min", 2)
    h1 = _candles(900, "1h", 3)
    feats = build_features_v2(m5, m15, h1)
    assert FEATURE_VERSION == "v2"
    assert list(feats.columns) == ALL_FEATURES
    assert len(feats.columns) == 37
    assert not feats.isna().any().any()
    assert feats.index.max() <= m15.index.max()


def test_truncating_future_candles_does_not_change_past_features():
    m5 = _candles(3000, "5min", 4)
    m15 = _candles(900, "15min", 5)
    h1 = _candles(900, "1h", 6)
    full = build_features_v2(m5, m15, h1)
    cut = m15.index[500]

    def trunc(df: pd.DataFrame) -> pd.DataFrame:
        return df.loc[:cut]

    past = build_features_v2(trunc(m5), trunc(m15), trunc(h1))
    common = full.index.intersection(past.index)
    assert len(common) > 100
    pd.testing.assert_frame_equal(full.loc[common], past.loc[common])
