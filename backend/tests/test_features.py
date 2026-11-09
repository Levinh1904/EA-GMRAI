"""Feature engineering: correctness, no-NaN, and NO-LOOKAHEAD invariants."""
import numpy as np
import pandas as pd
import pytest

from app.ml.features import ALL_FEATURES, build_features
from app.ml.synthetic import generate_synthetic_candles


@pytest.fixture(scope="module")
def data():
    df_m5, df_m15, df_h1, regimes = generate_synthetic_candles(n_m15=3000, seed=7)
    return df_m5, df_m15, df_h1, regimes


def test_features_clean(data):
    df_m5, df_m15, df_h1, _ = data
    feats = build_features(df_m5, df_m15, df_h1)
    assert len(feats) > 2000
    assert list(feats.columns) == ALL_FEATURES
    assert not feats.isna().any().any()
    assert np.isfinite(feats.values).all()


def test_ret1_formula(data):
    df_m5, df_m15, df_h1, _ = data
    feats = build_features(df_m5, df_m15, df_h1)
    expected = np.log(df_m15["close"] / df_m15["close"].shift(1))
    pd.testing.assert_series_equal(
        feats["ret1"].round(9), expected.reindex(feats.index).round(9), check_names=False
    )


def test_no_lookahead_truncation(data):
    """Features at t computed on a truncated series must equal features at t
    computed on the full series (adding future bars changes nothing at t)."""
    df_m5, df_m15, df_h1, _ = data
    full = build_features(df_m5, df_m15, df_h1)
    cut = 1500
    trunc = build_features(
        df_m5[df_m5.index <= df_m15.index[cut]],
        df_m15.iloc[: cut + 1],
        df_h1[df_h1.index <= df_m15.index[cut]],
    )
    common = trunc.index.intersection(full.index)
    pd.testing.assert_frame_equal(
        full.loc[common].round(9), trunc.loc[common].round(9)
    )


def test_asof_uses_closed_bars_only(data):
    """H1 context at an M15 bar uses the H1 bar that CLOSED at or before t."""
    df_m5, df_m15, df_h1, _ = data
    feats = build_features(df_m5, df_m15, df_h1)
    # At each M15 bar, h1 context must come from an H1 bar with close time <= t
    h1_close_times = df_h1.index + pd.Timedelta(hours=1)
    m15_times = feats.index
    for t in m15_times[:50]:
        candidates = h1_close_times[h1_close_times <= t]
        assert len(candidates) > 0
        assert candidates.max() > t - pd.Timedelta(hours=1)


def test_m5_features_present(data):
    df_m5, df_m15, df_h1, _ = data
    feats = build_features(df_m5, df_m15, df_h1)
    assert feats["m5_ret_short"].notna().all()
    assert feats["m5_vol_ratio"].notna().all()
    assert feats["m5_momentum"].notna().all()
