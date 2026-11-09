"""Regime engine: hysteresis, confirmation, early trend, threshold tuning."""
import numpy as np
import pandas as pd
import pytest

from app.ml.regime_engine import (
    EngineParams,
    EngineState,
    combine_scores,
    optimize_thresholds,
    run_engine_over_time,
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
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2)
    rows = [_row(0.7, 0.1)] * 10
    engine = run_engine_over_time(rows, params)
    assert engine["regime"].iloc[0] == "SIDEWAYS"  # first bar: PENDING_CONFIRM
    assert engine["regime"].iloc[1] == "TREND_UP"  # confirmed on 2nd bar
    assert (engine["regime"].iloc[2:] == "TREND_UP").all()


def test_hysteresis_hold_and_exit():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2)
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
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=3, theta_early=0.35, delta_early=0.1)
    rows = [_row(0.1, 0.1)] * 5 + [_row(0.5, 0.1)] * 1  # sharp rise but below enter
    engine = run_engine_over_time(rows, params)
    assert engine["regime"].iloc[5] == "EARLY_TREND_UP"
    assert engine["regime"].iloc[4] == "SIDEWAYS"


def test_engine_state_persistence():
    params = EngineParams(theta_enter=0.6, theta_exit=0.5, confirm_bars=2)
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
