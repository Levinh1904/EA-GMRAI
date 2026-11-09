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
