"""Current-state detector + engine override.

The detector answers "what is happening now" from closed bars only. These tests
lock the two properties that matter: it never fires on weak/conflicting
evidence, and when it IS confident the engine stops reporting SIDEWAYS
mid-trend.
"""
import numpy as np
import pandas as pd
import pytest

from app.ml.regime_engine import EngineParams, EngineState, run_engine_over_time
from app.ml.state_detector import (
    StateDetectorConfig,
    compute_state_inputs,
    detect_state,
    detect_state_series,
)


# ---------------------------------------------------------------------------
# Detector logic
# ---------------------------------------------------------------------------

def test_strong_down_state_is_detected():
    state, strength, reason = detect_state(displacement=-1.2, slope=-0.8, adx_norm=0.45)
    assert state == "TREND_DOWN"
    assert strength > 0.5
    assert reason in ("adx_displacement", "impulse")


def test_strong_up_state_is_detected():
    state, strength, _ = detect_state(displacement=0.9, slope=0.7, adx_norm=0.38)
    assert state == "TREND_UP"
    assert strength > 0.5


def test_flat_market_is_sideways():
    state, strength, reason = detect_state(displacement=0.05, slope=0.02, adx_norm=0.18)
    assert state == "SIDEWAYS"
    assert strength == 0.0
    assert reason == "no_directional_evidence"


def test_low_adx_with_small_displacement_is_not_a_trend():
    """Displacement alone, without ADX support, must not label a trend."""
    state, _, _ = detect_state(displacement=0.45, slope=0.30, adx_norm=0.10)
    assert state == "SIDEWAYS"


def test_conflicting_signals_are_sideways():
    """Displacement up but slope down -> contradictory, never a trend."""
    state, _, reason = detect_state(displacement=1.5, slope=-0.9, adx_norm=0.6)
    assert state == "SIDEWAYS"
    assert reason == "no_directional_evidence"


def test_missing_inputs_degrade_to_sideways():
    for args in [(None, 0.5, 0.3), (0.5, None, 0.3), (0.5, 0.5, None),
                 (np.nan, 0.5, 0.3), (0.5, np.inf, 0.3)]:
        state, strength, reason = detect_state(*args)
        assert state == "SIDEWAYS"
        assert strength == 0.0
        assert reason == "insufficient_input"


def test_impulse_without_adx_still_detects():
    """A violent move is a trend even before ADX catches up."""
    state, _, reason = detect_state(displacement=1.4, slope=0.6, adx_norm=0.15)
    assert state == "TREND_UP"
    assert reason == "impulse"


# ---------------------------------------------------------------------------
# Causality: detection at bar t must not depend on bars after t
# ---------------------------------------------------------------------------

def _synthetic_df(n=400, seed=7):
    rng = np.random.default_rng(seed)
    # trending down then up, with noise
    trend = np.concatenate([np.linspace(0, -30, n // 2), np.linspace(-30, 10, n // 2)])
    close = 2000 + trend + rng.normal(0, 1.5, n).cumsum() * 0.2
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.5, n),
            "high": close + 2,
            "low": close - 2,
            "close": close,
        },
        index=idx,
    )


def test_state_series_is_causal_under_truncation():
    df = _synthetic_df()
    full = detect_state_series(df)
    cut = 300
    truncated = detect_state_series(df.iloc[:cut])
    # Only bars visible in the truncated run can be compared; each must match
    # the full-history classification for that same bar.
    overlap = full.index.intersection(truncated.index)
    assert len(overlap) > 100
    pd.testing.assert_series_equal(
        full.loc[overlap, "state"], truncated.loc[overlap, "state"], check_names=False
    )


def test_state_inputs_use_only_past_bars():
    df = _synthetic_df()
    cfg = StateDetectorConfig()
    a = compute_state_inputs(df, cfg)
    b = compute_state_inputs(df.iloc[:250], cfg)
    overlap = a.index.intersection(b.index)
    pd.testing.assert_frame_equal(a.loc[overlap], b.loc[overlap])


def test_state_series_detects_a_real_trend():
    df = _synthetic_df()
    states = detect_state_series(df)
    counts = states["state"].value_counts()
    # The synthetic series holds a long down-move then a long up-move; the
    # detector must find trend bars in at least one direction and must not
    # label the whole series as trend (that would mean no filtering at all).
    trend_bars = counts.get("TREND_DOWN", 0) + counts.get("TREND_UP", 0)
    assert trend_bars > 20
    assert counts.get("SIDEWAYS", 0) > trend_bars / 2


# ---------------------------------------------------------------------------
# Engine override
# ---------------------------------------------------------------------------

def _score_row(**kw):
    base = {
        "p_up": 0.1, "p_down": 0.1, "p_side": 0.8, "p_trans": 0.0,
        "p_highvol": 0.0, "agreement": 0.9,
    }
    base.update(kw)
    return base


def test_engine_holds_sideways_without_detector():
    params = EngineParams(state_override_strength=0.45)
    rows = [_score_row() for _ in range(5)]
    out = run_engine_over_time(rows, params)
    assert (out["regime"] == "SIDEWAYS").all()


def test_engine_override_reports_ongoing_trend():
    """With a confident detector, SIDEWAYS is replaced by the running trend."""
    params = EngineParams(state_override_strength=0.45)
    row = _score_row(state="TREND_DOWN", state_strength=0.8)
    out = EngineState(params).step(row)
    assert out["regime"] == "TREND_DOWN"
    assert "STATE_DETECTOR_OVERRIDE" in out["reason_codes"]
    assert out["confidence"] >= 0.8


def test_engine_override_respects_strength_threshold():
    params = EngineParams(state_override_strength=0.60)
    weak = _score_row(state="TREND_UP", state_strength=0.30)
    assert EngineState(params).step(weak)["regime"] == "SIDEWAYS"


def test_engine_override_can_be_disabled():
    params = EngineParams(state_override_strength=0.0)
    row = _score_row(state="TREND_UP", state_strength=0.95)
    assert EngineState(params).step(row)["regime"] == "SIDEWAYS"


def test_override_does_not_replace_high_volatility():
    """HIGH_VOLATILITY is a base regime but carries different meaning here:
    only SIDEWAYS/TRANSITION are overridden, never a volatility warning."""
    params = EngineParams(state_override_strength=0.45)
    row = _score_row(p_highvol=0.9, p_side=0.05, state="TREND_UP", state_strength=0.9)
    out = EngineState(params).step(row)
    assert out["regime"] == "HIGH_VOLATILITY"
    assert "STATE_DETECTOR_OVERRIDE" not in out["reason_codes"]


def test_engine_params_roundtrip_includes_new_field():
    d = EngineParams(state_override_strength=0.33).to_dict()
    assert d["state_override_strength"] == 0.33
    assert EngineParams(**d).state_override_strength == 0.33
