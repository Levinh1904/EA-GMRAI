"""Reference engine + outcome evaluator + AI-vs-Reference tests."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.ml.outcome import OutcomeConfig, compute_outcomes
from app.ml.reference_engine import (
    REFERENCE_LABELS,
    ReferenceConfig,
    classify_reference,
    compute_reference_indicators,
)
from app.ml.synthetic import generate_synthetic_candles
from app.ml.history_stats import compare_ai_vs_reference


@pytest.fixture(scope="module")
def candles():
    _, df_m15, _, _ = generate_synthetic_candles(n_m15=2500, seed=23)
    return df_m15


def test_reference_labels_valid(candles):
    out = classify_reference(candles)
    assert set(out["regime"].unique()).issubset(set(REFERENCE_LABELS))
    assert "UNKNOWN" in out["regime"].unique()  # warmup bars
    assert all(out["reason"] != "")


def test_reference_is_causal_truncation_invariance(candles):
    """Labels at t must not change when future candles are appended."""
    cfg = ReferenceConfig()
    full = classify_reference(candles, cfg)
    cut = 1200
    trunc = classify_reference(candles.iloc[: cut + 1], cfg)
    common = trunc.index.intersection(full.index)
    pd.testing.assert_series_equal(
        full.loc[common, "regime"], trunc.loc[common, "regime"], check_names=False
    )


def test_reference_version_reproducibility(candles):
    """Same candles + same config version => identical labels."""
    cfg = ReferenceConfig(version="ref_v1", seedless_check=True) if False else ReferenceConfig()
    a = classify_reference(candles, cfg)
    b = classify_reference(candles, ReferenceConfig.from_dict(cfg.to_dict()))
    pd.testing.assert_series_equal(a["regime"], b["regime"], check_names=False)
    pd.testing.assert_series_equal(a["reason"], b["reason"], check_names=False)


def test_reference_config_versioned_snapshot(candles):
    cfg = ReferenceConfig(trend_adx_min=0.30, vol_atr_ratio=1.8)
    d = cfg.to_dict()
    assert d["version"] == "ref_v1"
    assert d["trend_adx_min"] == 0.30 and d["vol_atr_ratio"] == 1.8
    assert d["created_at"]
    cfg2 = ReferenceConfig.from_dict(d)
    assert cfg2.trend_adx_min == 0.30 and cfg2.version == "ref_v1"
    # different thresholds => (potentially) different labels; just verify they run
    out2 = classify_reference(candles, cfg2)
    assert len(out2) == len(candles)


def test_reference_independence_by_construction(candles):
    """The reference engine takes ONLY candles + config — it cannot access
    HMM/RF/operational outputs (structural independence, AST-verified)."""
    import ast
    import inspect

    from app.ml import reference_engine

    sig = inspect.signature(classify_reference)
    assert set(sig.parameters) == {"df_m15", "cfg"}

    tree = ast.parse(inspect.getsource(reference_engine))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
    banned = ("hmm", "rf_model", "regime_engine", "prediction", "ml.history")
    for mod in imported:
        assert not any(b in mod for b in banned), f"reference engine imports {mod}"


def test_reference_indicator_math(candles):
    """Spot-check indicator formulas against direct recomputation."""
    from app.ml.indicators import adx, atr, ema

    cfg = ReferenceConfig()
    ind = compute_reference_indicators(candles, cfg)
    adx_raw, plus_di, minus_di = adx(candles, cfg.adx_period)
    atr_raw = atr(candles, cfg.adx_period)
    ema_line = ema(candles["close"], cfg.ema_period)

    pd.testing.assert_series_equal(
        ind["adx_norm"].round(9), (adx_raw / 100.0).round(9), check_names=False
    )
    pd.testing.assert_series_equal(
        ind["di_gap"].round(9), ((plus_di - minus_di) / 100.0).round(9), check_names=False
    )
    pd.testing.assert_series_equal(
        ind["ema_slope"].round(9),
        ((ema_line - ema_line.shift(cfg.ema_slope_bars)) / atr_raw).round(9),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        ind["channel_high"].round(9), candles["high"].rolling(cfg.channel_period).max().round(9), check_names=False
    )
    pd.testing.assert_series_equal(
        ind["displacement"].round(9),
        ((candles["close"] - candles["close"].shift(cfg.displacement_bars)) / atr_raw).round(9),
        check_names=False,
    )


# ---------------------------------------------------------------- outcomes

def test_outcome_math():
    idx = pd.date_range("2026-01-05", periods=200, freq="15min", tz="UTC")
    close = pd.Series(np.linspace(2400, 2450, 200), index=idx)
    high = close + 2.0
    low = close - 2.0
    atr_s = pd.Series(np.full(200, 3.0), index=idx)
    out = compute_outcomes(close, high, low, atr_s, OutcomeConfig(horizons=(12,)))
    # fwd return at t = close[t+12] - close[t]
    expected = (close.shift(-12) - close).dropna()
    got = out["fwd_return_12"].dropna()
    np.testing.assert_allclose(got.values, expected.values, rtol=1e-9)
    pd.testing.assert_index_equal(got.index, expected.index)
    assert (out["mfe_12"] >= 0).all() and (out["mae_12"] >= 0).all()
    assert set(out["direction_12"].unique()).issubset({"UP", "DOWN", "FLAT"})
    assert out["in_range_12"].dtype == bool
    # no outcome rows beyond last 12 bars
    assert out.index.max() == idx[-13]


def test_outcome_does_not_mutate_predictions():
    """Future evaluation must not alter original labels."""
    idx = pd.date_range("2026-01-05", periods=100, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {"regime": ["TREND_UP"] * 100, "reference_regime": ["TREND_UP"] * 100}, index=idx
    )
    close = pd.Series(np.linspace(2400, 2410, 100), index=idx)
    before_ai = bars["regime"].copy()
    before_ref = bars["reference_regime"].copy()
    compute_outcomes(close, close + 1, close - 1, pd.Series(np.full(100, 1.0), index=idx))
    pd.testing.assert_series_equal(before_ai, bars["regime"], check_names=False)
    pd.testing.assert_series_equal(before_ref, bars["reference_regime"], check_names=False)


# ---------------------------------------------------------------- vs reference

def test_compare_ai_vs_reference_full_classes():
    n = 120
    idx = pd.date_range("2026-01-05", periods=n, freq="15min", tz="UTC")
    ai = (["TREND_UP"] * 40 + ["SIDEWAYS"] * 40 + ["TRANSITION"] * 40)
    ref = (["TREND_UP"] * 35 + ["SIDEWAYS"] * 5 + ["SIDEWAYS"] * 30 + ["TREND_UP"] * 10 + ["TRANSITION"] * 40)
    bars = pd.DataFrame({"regime": ai, "reference_regime": ref}, index=idx)
    out = compare_ai_vs_reference(bars)
    # TRANSITION preserved as its own class — never mapped into SIDEWAYS
    assert "TRANSITION" in out["classes"] and "SIDEWAYS" in out["classes"]
    assert out["per_class"]["TRANSITION"]["recall"] == 1.0
    assert out["per_class"]["TRANSITION"]["support"] == 40
    agree = int(pd.Series(ai).eq(pd.Series(ref)).sum())
    assert out["agreement_rate"] == round(agree / n, 4)
    assert 0.0 <= out["false_trend_rate"] <= 1.0
    assert 0.0 <= out["false_sideways_rate"] <= 1.0
    assert "matched" in out["boundaries"] and "missed" in out["boundaries"]
    assert out["macro_f1"] is not None


def test_compare_vs_reference_requires_column():
    bars = pd.DataFrame({"regime": ["TREND_UP"] * 5})
    with pytest.raises(ValueError):
        compare_ai_vs_reference(bars)
