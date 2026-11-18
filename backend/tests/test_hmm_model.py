"""HMM training, state statistics and semantic mapping."""
import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

from app.ml.features import M15_FEATURES, build_features
from app.ml.hmm_inference import from_hmmlearn
from app.ml.hmm_model import (
    map_states,
    save_hmm_artifact,
    semantic_probabilities,
    state_statistics,
    train_hmm,
)
from app.ml.synthetic import generate_synthetic_candles

ALLOWED_REGIMES = {"SIDEWAYS", "TREND_UP", "TREND_DOWN", "TRANSITION", "HIGH_VOLATILITY", "UNKNOWN"}


@pytest.fixture(scope="module")
def hmm_inputs():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=4000, seed=11)
    feats = build_features(df_m5, df_m15, df_h1)
    X = StandardScaler().fit_transform(feats[M15_FEATURES].values.astype(np.float64))
    return feats, X


def test_train_hmm_shapes(hmm_inputs):
    feats, X = hmm_inputs
    model, loglik = train_hmm(X, n_states=5, n_init=5, seed=42, n_iter=100)
    assert np.isfinite(loglik)
    assert model.startprob_.shape == (5,)
    assert model.transmat_.shape == (5, 5)
    assert model.means_.shape == (5, 7)
    # hmmlearn getter returns FULL covariance matrices even for "diag"
    assert np.asarray(model.covars_).shape == (5, 7, 7)
    diag = np.diagonal(np.asarray(model.covars_), axis1=1, axis2=2)
    assert diag.shape == (5, 7)
    np.testing.assert_allclose(model.transmat_.sum(axis=1), 1.0, atol=1e-8)


def test_state_statistics_and_mapping(hmm_inputs):
    feats, X = hmm_inputs
    model, _ = train_hmm(X, n_states=5, n_init=5, seed=42, n_iter=100)
    posterior = from_hmmlearn(model).posterior(X)
    stats = state_statistics(feats, posterior, 5)
    assert set(stats.keys()) == {str(i) for i in range(5)}
    for s in stats.values():
        assert "occupancy" in s and "ret1_mean" in s and "evidence" in s

    mapping = map_states(stats, 5)
    assert set(mapping.keys()) == {str(i) for i in range(5)}
    for m in mapping.values():
        assert m["regime"] in ALLOWED_REGIMES
        assert "reason" in m and "evidence" in m
    # occupancy must sum to ~1 across states
    assert abs(sum(s["occupancy"] for s in stats.values()) - 1.0) < 1e-6


def test_semantic_probabilities_sum(hmm_inputs):
    feats, X = hmm_inputs
    model, _ = train_hmm(X, n_states=5, n_init=5, seed=42, n_iter=100)
    posterior = from_hmmlearn(model).posterior(X)
    stats = state_statistics(feats, posterior, 5)
    mapping = map_states(stats, 5)
    probs = semantic_probabilities(posterior[-1], mapping)
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_hmm_artifact_roundtrip(tmp_path, hmm_inputs):
    feats, X = hmm_inputs
    model, _ = train_hmm(X, n_states=5, n_init=3, seed=1, n_iter=50)
    params = {
        "startprob": model.startprob_.tolist(),
        "transmat": model.transmat_.tolist(),
        "means": model.means_.tolist(),
        "covars_diag": np.diagonal(np.asarray(model.covars_), axis1=1, axis2=2).tolist(),
    }
    path = tmp_path / "model.json"
    save_hmm_artifact(
        path, params, [0.0] * 7, [1.0] * 7, M15_FEATURES, {"0": {"regime": "SIDEWAYS", "reason": "x", "evidence": {}}}, {"n_states": 5}
    )
    from app.ml.hmm_model import hmm_filter_from_artifact, load_hmm_artifact

    art = load_hmm_artifact(path)
    flt = hmm_filter_from_artifact(art)
    post = flt.posterior(X[:10])
    assert post.shape == (10, 5)


# ---------------------------------------------------------------------------
# Regression: a directional state with a small per-bar return drift must still
# be recognised as a trend (previously it was mapped to UNKNOWN, so the HMM
# never emitted TREND_UP at all and every live signal lagged the market).
# ---------------------------------------------------------------------------

def _state(**kw) -> dict:
    base = {
        "n_obs": 500,
        "occupancy": 0.2,
        "ret1_mean": 0.0,
        "ret1_std": 0.001,
        "adx_mean": 0.22,
        "ema_slope_mean": 0.0,
        "efficiency_mean": 0.1,
        "atr_ratio_mean": 1.0,
        "di_gap_mean": 0.0,
        "duration_mean": 12.0,
        "evidence": "ok",
    }
    base.update(kw)
    return base


def test_directional_state_maps_to_trend_up_despite_small_z():
    """Real artifact case: slope +0.54, di_gap +0.137, adx 0.372, z only 0.196."""
    stats = {
        "0": _state(),  # baseline flat
        "1": _state(ret1_mean=0.000195, ret1_std=0.000996, adx_mean=0.372,
                    ema_slope_mean=0.538, di_gap_mean=0.137),
        "2": _state(ret1_mean=-0.00015, ret1_std=0.000642, adx_mean=0.364,
                    ema_slope_mean=-0.434, di_gap_mean=-0.117),
        "3": _state(),
        "4": _state(),
    }
    m = map_states(stats, 5)
    assert m["1"]["regime"] == "TREND_UP", m["1"]
    assert m["1"]["reason"] == "directional_score_up"
    assert m["2"]["regime"] == "TREND_DOWN", m["2"]
    # Directional score is reported so the decision is auditable.
    assert m["1"]["direction_score"] > 0 > m["2"]["direction_score"]


def test_low_adx_never_becomes_trend():
    """A strong slope with no ADX must not be sold as a trend (ADX gate)."""
    stats = {
        "0": _state(ema_slope_mean=3.0, di_gap_mean=0.5, adx_mean=0.05),
        "1": _state(), "2": _state(), "3": _state(), "4": _state(),
    }
    m = map_states(stats, 5)
    assert m["0"]["regime"] != "TREND_UP", m["0"]


def test_flat_low_adx_state_stays_sideways():
    stats = {str(i): _state() for i in range(5)}
    m = map_states(stats, 5)
    assert all(v["regime"] == "SIDEWAYS" for v in m.values()), m


def test_mapping_still_emits_high_volatility_and_unknown():
    stats = {
        "0": _state(atr_ratio_mean=2.5),  # volatility outlier
        "1": _state(adx_mean=0.5, ema_slope_mean=0.05, di_gap_mean=0.01,
                    ret1_mean=0.0002, ret1_std=0.001, duration_mean=20.0),
        "2": _state(), "3": _state(), "4": _state(),
    }
    m = map_states(stats, 5)
    assert m["0"]["regime"] == "HIGH_VOLATILITY"
    # Mid-ADX, no real direction, long duration -> UNKNOWN (not forced)
    assert m["1"]["regime"] == "UNKNOWN", m["1"]


def test_semantic_probs_expose_both_directions():
    """Both TREND_UP and TREND_DOWN must be reachable from a posterior."""
    stats = {
        "0": _state(),
        "1": _state(ema_slope_mean=0.538, di_gap_mean=0.137, adx_mean=0.372,
                    ret1_mean=0.0002, ret1_std=0.001),
        "2": _state(ema_slope_mean=-0.434, di_gap_mean=-0.117, adx_mean=0.364,
                    ret1_mean=-0.0002, ret1_std=0.001),
        "3": _state(), "4": _state(),
    }
    m = map_states(stats, 5)
    probs = semantic_probabilities(np.array([0.1, 0.6, 0.3, 0.0, 0.0]), m)
    assert probs.get("TREND_UP", 0.0) > 0.0
    assert probs.get("TREND_DOWN", 0.0) > 0.0
