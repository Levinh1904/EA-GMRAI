"""Regime engine: hysteresis, confirmation, early trend, threshold tuning."""
import numpy as np
import pandas as pd
import pytest

from app.ml.regime_engine import (
    EngineParams,
    EngineState,
    collapse_short_trends,
    combine_scores,
    optimize_thresholds,
    run_engine_over_time,
    run_engine_over_time_causal,
)


def _row(up, down, side=None, trans=0.0, highvol=0.0, agreement=0.9):
    side = 1.0 - up - down - trans - highvol if side is None else side
    return {"p_up": up, "p_down": down, "p_side": side, "p_trans": trans, "p_highvol": highvol, "agreement": agreement}


def test_combine_scores_normalized():
    hmm = {"TREND_UP": 0.6, "TREND_DOWN": 0.1, "SIDEWAYS": 0.3}
    rf = {"TREND_UP": 0.8, "TREND_DOWN": 0.1, "SIDEWAYS": 0.1}
    out = combine_scores(hmm, rf, 0.5)
    assert abs(out["p_up"] - 0.7) < 1e-9
    total = out["p_up"] + out["p_down"] + out["p_side"] + out["p_trans"] + out["p_highvol"]
    assert abs(total - 1.0) < 1e-9
    assert 0.0 <= out["agreement"] <= 1.0


def test_confirmation_then_entry():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2, min_signal_bars=1)
    rows = [_row(0.7, 0.1)] * 10
    engine = run_engine_over_time(rows, params)
    assert engine["regime"].iloc[0] == "SIDEWAYS"  # first bar: PENDING_CONFIRM
    assert engine["regime"].iloc[1] == "TREND_UP"  # confirmed on 2nd bar
    assert (engine["regime"].iloc[2:] == "TREND_UP").all()


def test_hysteresis_hold_and_exit():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2, min_signal_bars=1)
    rows = [_row(0.7, 0.1)] * 3 + [_row(0.52, 0.2)] * 2  # above exit -> hold
    rows += [_row(0.4, 0.3)] * 1  # first below-exit bar: still hold
    rows += [_row(0.4, 0.3)] * 1  # second below-exit bar: exit
    engine = run_engine_over_time(rows, params)
    regimes = engine["regime"].tolist()
    assert regimes[3:5] == ["TREND_UP", "TREND_UP"]
    assert regimes[5] == "TREND_UP"  # exit_count=1 -> still held
    assert regimes[6] == "SIDEWAYS"
    assert "EXIT_BELOW_THRESHOLD" in engine["reason_codes"].iloc[6]


def test_early_trend_advisory():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=3, theta_early=0.35, delta_early=0.1, min_signal_bars=1)
    rows = [_row(0.1, 0.1)] * 5 + [_row(0.5, 0.1)] * 1  # sharp rise but below enter
    engine = run_engine_over_time(rows, params)
    assert engine["regime"].iloc[5] == "EARLY_TREND_UP"
    assert engine["regime"].iloc[4] == "SIDEWAYS"


def test_early_trend_confidence_is_directional_not_zero():
    """EARLY_TREND_* used to report confidence 0.0 regardless of probability."""
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=3, theta_early=0.35, delta_early=0.1, min_signal_bars=1)
    rows = [_row(0.1, 0.1)] * 5 + [_row(0.5, 0.1)] * 1
    engine = run_engine_over_time(rows, params)
    assert engine["regime"].iloc[5] == "EARLY_TREND_UP"
    assert engine["confidence"].iloc[5] > 0.0
    # The reported confidence must match the direction it points at.
    assert abs(engine["confidence"].iloc[5] - 0.5) < 0.06

    rows_down = [_row(0.1, 0.1)] * 5 + [_row(0.1, 0.5)] * 1
    engine_down = run_engine_over_time(rows_down, params)
    assert engine_down["regime"].iloc[5] == "EARLY_TREND_DOWN"
    assert engine_down["confidence"].iloc[5] > 0.0


def test_engine_state_persistence():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2, min_signal_bars=1)
    st = EngineState(params)
    out1 = st.step(_row(0.7, 0.1))
    out2 = st.step(_row(0.7, 0.1))
    assert out1["regime"] == "SIDEWAYS"
    assert out2["regime"] == "TREND_UP"
    snap = out2["engine_state"]
    st2 = EngineState(params)
    st2.restore(snap)
    out3 = st2.step(_row(0.7, 0.1))
    assert out3["regime"] == "TREND_UP"
    assert "HYSTERESIS_HOLD" in out3["reason_codes"]


def test_optimize_thresholds():
    rng = np.random.default_rng(2)
    rows, labels = [], []
    for i in range(300):
        if i < 100:
            up, down = 0.75, 0.05
            label = "TREND_UP"
        elif i < 200:
            up, down = 0.05, 0.75
            label = "TREND_DOWN"
        else:
            up, down = 0.15, 0.15
            label = "SIDEWAYS"
        up += rng.normal(0, 0.08)
        down += rng.normal(0, 0.08)
        rows.append(_row(max(up, 0), max(down, 0)))
        labels.append(label)
    y = pd.Series(labels)
    params, score, results = optimize_thresholds(rows, y)
    assert params is not None
    assert np.isfinite(score)
    assert len(results) == 36
    # Tuned engine must beat chance-level macro F1 (3 classes => > 0.33)
    eng = run_engine_over_time(rows, params)
    pred = eng["regime"].replace({"TRANSITION": "SIDEWAYS", "HIGH_VOLATILITY": "SIDEWAYS", "UNKNOWN": "SIDEWAYS", "EARLY_TREND_UP": "SIDEWAYS", "EARLY_TREND_DOWN": "SIDEWAYS"})
    from sklearn.metrics import f1_score

    f1 = f1_score(y, pred, labels=["TREND_UP", "TREND_DOWN", "SIDEWAYS"], average="macro", zero_division=0)
    assert f1 > 0.5


# ---------------------------------------------------------------------------
# Short-trend collapse.
#
# Measured on 23k real M15 bars: trend runs of 1-8 bars "won" only 24-32% of
# the time when scored from signal start to segment end (i.e. price reversed
# before the segment finished), while 9+ bar runs won 65-99%. A short run is
# noise, so it is published as SIDEWAYS rather than as a signal that immediately
# reverses.
# ---------------------------------------------------------------------------

def test_collapse_short_trends_relabels_runs_below_min():
    regimes = ["SIDEWAYS", "TREND_DOWN", "TREND_DOWN", "SIDEWAYS", "TREND_UP"]
    out, collapsed = collapse_short_trends(regimes, min_bars=3)
    assert out == ["SIDEWAYS"] * 5
    assert collapsed == 2


def test_collapse_keeps_long_enough_trends():
    regimes = ["SIDEWAYS"] + ["TREND_UP"] * 5 + ["SIDEWAYS"]
    out, collapsed = collapse_short_trends(regimes, min_bars=3)
    assert out == regimes
    assert collapsed == 0


def test_collapse_mixed_runs():
    regimes = (
        ["TREND_UP"] * 2          # too short -> collapsed
        + ["SIDEWAYS"]
        + ["TREND_DOWN"] * 4      # long enough -> kept
        + ["TREND_UP"] * 1        # too short -> collapsed
    )
    out, collapsed = collapse_short_trends(regimes, min_bars=3)
    expected = (
        ["SIDEWAYS"] * 2
        + ["SIDEWAYS"]
        + ["TREND_DOWN"] * 4
        + ["SIDEWAYS"]
    )
    assert out == expected
    assert collapsed == 2


def test_collapse_is_noop_when_disabled():
    regimes = ["TREND_UP", "TREND_DOWN"]
    out, collapsed = collapse_short_trends(regimes, min_bars=1)
    assert out == regimes
    assert collapsed == 0


def test_collapse_never_invents_a_trend():
    """Collapsing may only remove trend labels, never create one."""
    regimes = ["SIDEWAYS", "TREND_UP", "SIDEWAYS", "TREND_DOWN", "SIDEWAYS"]
    out, _ = collapse_short_trends(regimes, min_bars=5)
    assert all(r == "SIDEWAYS" for r in out)


def test_engine_run_applies_min_signal_bars():
    """A 4-bar trend inside a longer series is suppressed end-to-end."""
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=1,
                          min_signal_bars=9)
    rows = [_row(0.1, 0.1)] * 5 + [_row(0.8, 0.05)] * 4 + [_row(0.1, 0.1)] * 5
    eng = run_engine_over_time(rows, params)
    assert (eng["regime"] == "SIDEWAYS").all()


def test_engine_run_keeps_long_trend():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=1,
                          min_signal_bars=9)
    rows = [_row(0.1, 0.1)] * 2 + [_row(0.8, 0.05)] * 12 + [_row(0.1, 0.1)] * 2
    eng = run_engine_over_time(rows, params)
    assert (eng["regime"].iloc[2:14] == "TREND_UP").all()


# ---------------------------------------------------------------------------
# Causality of the short-trend filter.
#
# The retrospective version needs a run's TOTAL length to decide its first bar,
# which is look-ahead: at bar 0 of a 5-bar run nothing differs from bar 0 of a
# 40-bar run. That inflated every accuracy figure derived from history labels
# and made history disagree with what live could produce.
# ---------------------------------------------------------------------------

def test_causal_collapse_never_uses_future_bars():
    from app.ml.regime_engine import collapse_short_trends_causal

    # Same prefix, two different futures: the prefix labels must be identical.
    short = ["SIDEWAYS"] * 2 + ["TREND_DOWN"] * 3
    long = ["SIDEWAYS"] * 2 + ["TREND_DOWN"] * 30
    out_short, _ = collapse_short_trends_causal(short, 9)
    out_long, _ = collapse_short_trends_causal(long, 9)
    # Bars 0..4 are the same input; the label at each of those indices must match.
    for i in range(len(short)):
        if i < len(short):
            assert out_short[i] == out_long[i], (
                f"bar {i} label depends on how long the run eventually became "
                f"({out_short[i]} vs {out_long[i]}) — that is look-ahead"
            )


def test_causal_collapse_activates_once_run_is_long_enough():
    from app.ml.regime_engine import collapse_short_trends_causal

    regimes = ["SIDEWAYS"] + ["TREND_UP"] * 6
    out, _ = collapse_short_trends_causal(regimes, 4)
    # 1,2,3 bars of run -> still SIDEWAYS; from the 4th bar -> TREND_UP.
    assert out[1:4] == ["SIDEWAYS", "SIDEWAYS", "SIDEWAYS"]
    assert out[4:] == ["TREND_UP", "TREND_UP", "TREND_UP"]


def test_causal_collapse_resets_on_non_trend():
    from app.ml.regime_engine import collapse_short_trends_causal

    regimes = ["TREND_UP"] * 3 + ["SIDEWAYS"] + ["TREND_UP"] * 3
    out, _ = collapse_short_trends_causal(regimes, 2)
    assert out == ["SIDEWAYS", "TREND_UP", "TREND_UP", "SIDEWAYS", "SIDEWAYS", "TREND_UP", "TREND_UP"]


def test_causal_matches_retro_never_invents_extra_trends():
    """Causal may only REMOVE trend labels relative to raw, never add."""
    from app.ml.regime_engine import _trend_of, collapse_short_trends_causal

    regimes = (
        ["TREND_DOWN"] * 2
        + ["SIDEWAYS"]
        + ["TREND_UP"] * 12
        + ["TREND_DOWN"]
        + ["SIDEWAYS"] * 3
    )
    out, _ = collapse_short_trends_causal(regimes, 9)
    for raw, lab in zip(regimes, out):
        if _trend_of(lab) is not None:
            assert _trend_of(raw) == _trend_of(lab), "causal must not invent a trend"


def test_min_hold_bars_keeps_trend_after_probability_drop():
    params = EngineParams(
        theta_enter=0.6, theta_exit=0.5, confirm_bars=1, min_signal_bars=1, min_hold_bars=4
    )
    rows = [_row(0.7, 0.1)] * 2 + [_row(0.1, 0.1)] * 6
    eng = run_engine_over_time(rows, params)
    # Entry at bar 0, then held through the probability drop until the hold expires.
    assert list(eng["regime"].iloc[:4]) == ["TREND_UP"] * 4
    assert "MIN_HOLD" in eng["reason_codes"].iloc[2]
    assert eng["regime"].iloc[4] == "SIDEWAYS"


def test_causal_replay_is_prefix_invariant():
    params = EngineParams(
        theta_enter=0.55, theta_exit=0.35, confirm_bars=2, min_signal_bars=3
    )
    rows = (
        [_row(0.7, 0.1)] * 6
        + [_row(0.1, 0.7)] * 6
        + [_row(0.1, 0.1)] * 6
    )
    full = run_engine_over_time_causal(rows, params)["regime"].tolist()
    for k in range(1, len(rows) + 1):
        prefix = run_engine_over_time_causal(rows[:k], params)["regime"].tolist()
        assert prefix == full[:k], f"causal replay changed with future rows at k={k}"


def test_entry_gate_blocks_weak_displacement():
    params = EngineParams(
        theta_enter=0.55,
        theta_exit=0.35,
        confirm_bars=1,
        min_signal_bars=1,
        min_disp_signal=1.0,
    )
    weak = _row(0.8, 0.05)
    weak["state_displacement"] = 0.2
    weak["h1_trend_context"] = 0.5
    strong = _row(0.8, 0.05)
    strong["state_displacement"] = 1.5
    strong["h1_trend_context"] = 0.5
    out_weak = run_engine_over_time([weak] * 5, params)
    assert "TREND_UP" not in set(out_weak["regime"])
    assert any("ENTRY_FILTERED" in str(r) for r in out_weak["reason_codes"])
    out_strong = run_engine_over_time([strong] * 5, params)
    assert "TREND_UP" in set(out_strong["regime"])


def test_entry_hour_filter_blocks_outside_hours():
    params = EngineParams(
        theta_enter=0.55,
        theta_exit=0.35,
        confirm_bars=1,
        min_signal_bars=1,
        allowed_entry_hours_utc=[8, 14, 17],
    )
    outside = _row(0.9, 0.05)
    outside["hour_utc"] = 3
    inside = _row(0.9, 0.05)
    inside["hour_utc"] = 8
    out_bad = run_engine_over_time([outside] * 5, params)
    assert "TREND_UP" not in set(out_bad["regime"])
    assert not any("EARLY_TREND" in str(r) for r in out_bad["regime"])
    assert any("HOUR_FILTERED" in str(r) for r in out_bad["reason_codes"])
    out_ok = run_engine_over_time([inside] * 5, params)
    assert "TREND_UP" in set(out_ok["regime"])


def test_long_side_filter_blocks_weak_h1():
    params = EngineParams(
        theta_enter=0.55,
        theta_exit=0.35,
        confirm_bars=1,
        min_signal_bars=1,
        long_min_h1_context=0.2,
    )
    weak = _row(0.9, 0.05)
    weak["h1_trend_context"] = 0.1
    strong = _row(0.9, 0.05)
    strong["h1_trend_context"] = 0.3
    out_weak = run_engine_over_time([weak] * 5, params)
    assert "TREND_UP" not in set(out_weak["regime"])
    assert any("LONG_FILTERED" in str(r) for r in out_weak["reason_codes"])
    out_strong = run_engine_over_time([strong] * 5, params)
    assert "TREND_UP" in set(out_strong["regime"])
