"""Walk-forward backtest engine — structural invariants + end-to-end run."""
from app.ml.backtest_engine import BacktestConfig, run_walk_forward
from app.ml.synthetic import generate_synthetic_candles

CFG = BacktestConfig(
    initial_train=1500,
    test_size=400,
    embargo=12,
    hmm_n_states=5,
    hmm_n_init=3,
    seed=7,
    rf_horizon=12,
    cost_usd=30.0,
    max_hold=24,
)


def test_walk_forward_insufficient_data():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=800, seed=1)
    import pytest

    with pytest.raises(ValueError):
        run_walk_forward(df_m5, df_m15, df_h1, CFG)


def test_walk_forward_end_to_end():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=2600, seed=5)
    report = run_walk_forward(df_m5, df_m15, df_h1, CFG)

    assert report["n_folds"] >= 2
    assert set(report["variant_comparison"].keys()) == {"hmm_only", "rf_only", "combined"}
    assert report["chosen_variant"] in {"hmm_only", "rf_only", "combined"}

    for fold in report["folds"]:
        # leakage invariant: train ends exactly `embargo` bars before test start
        assert fold["train_range"][1] == fold["test_range"][0] - CFG.embargo
        assert fold["subval_range"][0] < fold["subval_range"][1] <= fold["test_range"][0] - CFG.embargo
        for variant, vr in fold["variants"].items():
            assert 0.0 <= vr["classification"]["macro_f1"] <= 1.0
            assert 0.0 <= vr["false_trend_rate"] <= 1.0
            assert "trading" in vr and "n_trades" in vr["trading"]
            assert vr["params"]["theta_exit"] <= vr["params"]["theta_enter"]

    chosen = report["chosen_variant"]
    f1s = [f["variants"][chosen]["classification"]["macro_f1"] for f in report["folds"]]
    assert report["variant_comparison"][chosen]["macro_f1"]["mean"] == max(
        v["macro_f1"]["mean"] for v in report["variant_comparison"].values()
    )
    # sanity: mean f1 is a real value
    assert all(0.0 <= f <= 1.0 for f in f1s)
