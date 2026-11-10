"""Historical regime engine tests: segmentation, stats, causality."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.ml.history import HistoryConfig, build_segments, run_historical_inference
from app.ml.history_stats import (
    compare_runs,
    compare_vs_reference,
    duration_statistics,
    early_trend_analysis,
    multi_tf_context,
    period_aggregation,
    sideways_analysis,
    transition_count,
    transition_matrix,
    trend_analysis,
)


def _bars_df(regimes, start="2026-01-05T00:00:00Z", period_min=15, price=2400.0):
    n = len(regimes)
    ts = pd.date_range(start, periods=n, freq=f"{period_min}min", tz="UTC")
    price += np.arange(n) * 0.5
    return pd.DataFrame(
        {
            "ts": ts,
            "regime": regimes,
            "confidence": [0.7] * n,
            "permission": ["NO_TRADE"] * n,
            "hmm_state": [0] * n,
            "hmm_posterior": [np.ones(5) / 5] * n,
            "rf_probs": [{"SIDEWAYS": 0.4, "TREND_UP": 0.3, "TREND_DOWN": 0.3}] * n,
            "reason_codes": [["X"]] * n,
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price + 0.5,
            "atr_ratio": [1.0] * n,
            "adx_norm": [0.3] * n,
            "efficiency_ratio": [0.5] * n,
            "h1_trend_context": [0.2] * n,
            "m5_momentum": [0.1] * n,
        }
    ).set_index("ts")


def test_segmentation_basic():
    bars = _bars_df(["TREND_UP"] * 4 + ["SIDEWAYS"] * 3 + ["TREND_DOWN"] * 5)
    segs = build_segments(bars, 900)
    assert [s["regime"] for s in segs] == ["TREND_UP", "SIDEWAYS", "TREND_DOWN"]
    assert [s["bar_count"] for s in segs] == [4, 3, 5]
    assert [s["duration_minutes"] for s in segs] == [60, 45, 75]
    assert segs[0]["start_ts"] == bars.index[0] and segs[-1]["end_ts"] == bars.index[-1]


def test_segmentation_gap_split():
    bars = _bars_df(["TREND_UP"] * 10)
    # remove bars 4..6 -> creates a data gap inside the same regime
    bars = pd.concat([bars.iloc[:4], bars.iloc[7:]])
    segs = build_segments(bars, 900)
    assert len(segs) == 2
    assert segs[0]["regime"] == segs[1]["regime"] == "TREND_UP"
    assert segs[0]["split_reason"] == "data_gap"


def test_segmentation_segment_stats():
    bars = _bars_df(["TREND_UP"] * 5, price=2399.0)
    segs = build_segments(bars, 900)
    s = segs[0]
    assert s["start_price"] == bars["open"].iloc[0]
    assert s["end_price"] == bars["close"].iloc[-1]
    assert s["high_price"] == bars["high"].max()
    assert s["low_price"] == bars["low"].min()
    assert s["net_change"] == round(s["end_price"] - s["start_price"], 3)
    assert s["mfe"] >= 0 and s["mae"] >= 0


def test_duration_statistics():
    bars = _bars_df(["TREND_UP"] * 4 + ["SIDEWAYS"] * 2 + ["TREND_UP"] * 6)
    segs = build_segments(bars, 900)
    stats = duration_statistics(segs)
    up = stats["TREND_UP"]
    assert up["occurrences"] == 2
    assert up["total_minutes"] == 60 + 90
    assert stats["SIDEWAYS"]["occurrences"] == 1
    assert stats["SIDEWAYS"]["longest_minutes"] == 30
    assert abs(stats["TREND_UP"]["occupancy_pct"] + stats["SIDEWAYS"]["occupancy_pct"] - 100) < 0.01
    assert transition_count(segs) == 2


def test_transition_matrix():
    bars = _bars_df(["TREND_UP"] * 4 + ["SIDEWAYS"] * 2 + ["TREND_UP"] * 3 + ["TREND_DOWN"] * 3)
    segs = build_segments(bars, 900)
    tm = transition_matrix(segs)
    assert tm["counts"]["TREND_UP"]["SIDEWAYS"] == 1
    assert tm["counts"]["SIDEWAYS"]["TREND_UP"] == 1
    assert tm["counts"]["TREND_UP"]["TREND_DOWN"] == 1
    assert tm["rates"]["TREND_UP"]["SIDEWAYS"] == 0.5
    assert tm["total_transitions"] == 3


def test_sideways_breakouts():
    bars = _bars_df(
        ["SIDEWAYS"] * 10 + ["TREND_UP"] * 6 + ["SIDEWAYS"] * 10 + ["TREND_UP"] * 2 + ["SIDEWAYS"] * 10
    )
    segs = build_segments(bars, 900)
    out = sideways_analysis(segs)
    assert out["breakouts"] == 2
    assert out["false_breakouts"] == 1
    assert out["buckets"][">8h"] == 0
    assert sum(out["buckets"].values()) == 3


def test_early_trend_analysis():
    n = 60
    regimes = ["SIDEWAYS"] * 10 + ["EARLY_TREND_UP"] + ["SIDEWAYS"] * 8 + ["EARLY_TREND_UP"] + ["SIDEWAYS"] * 39
    bars = _bars_df(regimes)
    # realized labels: first early signal -> trend up develops; second -> nothing
    labels = pd.Series("SIDEWAYS", index=bars.index)
    labels.iloc[12:20] = "TREND_UP"  # after first signal (bar 10)
    out = early_trend_analysis(bars, labels, window=12)
    assert out["EARLY_TREND_UP"]["signals"] == 2
    assert out["EARLY_TREND_UP"]["confirmed"] == 1
    assert out["EARLY_TREND_UP"]["no_trend"] == 1
    assert out["EARLY_TREND_UP"]["success_rate_pct"] == 50.0


def test_period_aggregation_day_split():
    # bars crossing midnight: 3 bars 23:30, 23:45, 00:00(next day)
    ts = pd.to_datetime(
        ["2026-01-05T23:30:00Z", "2026-01-05T23:45:00Z", "2026-01-06T00:00:00Z"]
    ).tz_convert("UTC")
    bars = _bars_df(["TREND_UP", "TREND_UP", "SIDEWAYS"]).set_index(ts)
    bars = bars.loc[ts]
    segs = build_segments(bars, 900)
    out = period_aggregation(bars, segs, "day")
    rows = {r["period_start"][:10]: r for r in out["rows"]}
    assert rows["2026-01-05"]["trend_up_minutes"] == 30
    assert rows["2026-01-06"]["sideways_minutes"] == 15
    assert rows["2026-01-05"]["dominant_regime"] == "TREND_UP"


def test_multi_tf_context():
    bars = _bars_df(["TREND_UP"] * 4 + ["SIDEWAYS"] * 2)
    bars["h1_trend_context"] = [0.3, 0.3, -0.3, -0.3, 0.0, 0.0]
    bars["m5_momentum"] = [0.8, -0.8, 0.8, -0.8, 0.0, 0.0]
    out = multi_tf_context(bars)
    assert out["counts"]["CONSENSUS_UP"] == 1  # bar0: m15 UP, h1 UP, m5 UP
    assert out["counts"]["CONFLICT_BOTH"] == 1  # bar1: h1 DOWN, m5 DOWN
    assert out["counts"]["CONFLICT_H1"] == 1  # bar2
    assert out["counts"]["CONFLICT_M5"] == 1  # bar3
    assert len(out["sample"]) == 6


def test_compare_runs():
    a = _bars_df(["TREND_UP"] * 6 + ["SIDEWAYS"] * 4)
    b = _bars_df(["TREND_UP"] * 5 + ["TREND_DOWN"] * 5)
    out = compare_runs(a, b, "runA", "runB")
    assert out["overlap_bars"] == 10
    assert out["confusion_counts"]["TREND_UP"]["TREND_UP"] == 5
    assert out["confusion_counts"]["SIDEWAYS"]["TREND_DOWN"] == 4
    assert out["agreement_rate"] == 0.5


def test_compare_vs_reference():
    bars = _bars_df(["TREND_UP"] * 40 + ["SIDEWAYS"] * 40)
    labels = pd.Series("SIDEWAYS", index=bars.index)
    labels.iloc[:40] = "TREND_UP"
    out = compare_vs_reference(bars, labels)
    assert out["classification"]["accuracy"] == 1.0
    assert out["false_trend_rate"] == 0.0


# ---------------------------------------------------------------- causality

def _fake_hmm_artifact(n_states=5, seed=7):
    rng = np.random.default_rng(seed)
    return {
        "params": {
            "startprob": (rng.dirichlet(np.ones(n_states))).tolist(),
            "transmat": (rng.dirichlet(np.ones(n_states), size=n_states)).tolist(),
            "means": rng.normal(0, 1, (n_states, 7)).tolist(),
            "covars_diag": (np.abs(rng.normal(1, 0.3, (n_states, 7))) + 0.1).tolist(),
        },
        "scaler_mean": [0.0] * 7,
        "scaler_std": [1.0] * 7,
        "feature_columns": ["ret1", "ret4", "atr_ratio", "ema_slope", "efficiency_ratio", "adx_norm", "di_gap"],
        "state_mapping": {
            str(i): {"regime": r, "reason": "test", "evidence": {}}
            for i, r in enumerate(["SIDEWAYS", "TREND_UP", "TREND_DOWN", "TRANSITION", "HIGH_VOLATILITY"])
        },
        "meta": {"feature_version": "v1"},
    }


def _fake_rf(seed=3):
    from sklearn.ensemble import RandomForestClassifier

    rng = np.random.default_rng(seed)
    X = rng.normal(size=(300, 29))
    y = np.array(["TREND_DOWN", "SIDEWAYS", "TREND_UP"])[rng.integers(0, 3, 300)]
    clf = RandomForestClassifier(n_estimators=20, max_depth=6, random_state=seed)
    clf.fit(X, y)
    return clf


def test_inference_is_causal_truncation_invariance():
    """Regime at t must be identical whether computed on full or truncated
    history (filtered posterior + stateful engine = no lookahead)."""
    from app.ml.synthetic import generate_synthetic_candles

    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=1500, seed=11)
    art = _fake_hmm_artifact()
    rf = _fake_rf()
    engine_params = {
        "weight_hmm": 0.5, "theta_enter": 0.55, "theta_exit": 0.45,
        "confirm_bars": 2, "theta_early": 0.35, "delta_early": 0.1,
        "highvol_threshold": 0.45, "agreement_threshold": 0.8,
    }
    full = run_historical_inference(df_m5, df_m15, df_h1, art, rf, engine_params)
    cut = 800
    trunc = run_historical_inference(
        df_m5[df_m5.index <= df_m15.index[cut]],
        df_m15.iloc[: cut + 1],
        df_h1[df_h1.index <= df_m15.index[cut]],
        art, rf, engine_params,
    )
    common = trunc.index.intersection(full.index)
    pd.testing.assert_series_equal(full.loc[common, "regime"], trunc.loc[common, "regime"], check_names=False)


def test_trend_analysis_strength():
    bars = _bars_df(["TREND_UP"] * 8 + ["TREND_DOWN"] * 8 + ["TREND_UP"] * 8 + ["TREND_DOWN"] * 8)
    bars["efficiency_ratio"] = [0.9] * 8 + [0.8] * 8 + [0.2] * 8 + [0.3] * 8
    bars["adx_norm"] = [0.9] * 8 + [0.8] * 8 + [0.2] * 8 + [0.3] * 8
    segs = build_segments(bars, 900)
    out = trend_analysis(segs)
    dist = out["strength"]["distribution"]
    assert dist["TREND_UP|strong"] == 1 and dist["TREND_UP|weak"] == 1
    assert dist["TREND_DOWN|medium"] == 2


def test_period_aggregation_month_quarter_year():
    ts = pd.to_datetime(
        ["2026-01-05T23:30:00Z", "2026-01-31T23:45:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:15:00Z"]
    ).tz_convert("UTC")
    bars = _bars_df(["TREND_UP"] * 4).set_index(ts).loc[ts]
    segs = build_segments(bars, 900)
    for p in ("month", "quarter", "year"):
        out = period_aggregation(bars, segs, p)
        assert out["period"] == p and len(out["rows"]) >= 1
