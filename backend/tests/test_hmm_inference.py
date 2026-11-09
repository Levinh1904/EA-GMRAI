"""HMM inference: parity with hmmlearn + strict causality invariants."""
import numpy as np
import pytest
from hmmlearn.hmm import GaussianHMM

from app.ml.hmm_inference import HmmFilter, from_hmmlearn

rng = np.random.default_rng(123)


def _random_hmm(n_states=5, n_features=7):
    start = rng.dirichlet(np.ones(n_states))
    trans = rng.dirichlet(np.ones(n_states), size=n_states)
    means = rng.normal(0, 1, size=(n_states, n_features))
    vars_ = np.abs(rng.normal(1, 0.3, size=(n_states, n_features))) + 0.1
    return HmmFilter(start, trans, means, vars_)


def test_posterior_sums_to_one():
    flt = _random_hmm()
    X = rng.normal(size=(100, 7))
    post = flt.posterior(X)
    assert post.shape == (100, 5)
    np.testing.assert_allclose(post.sum(axis=1), 1.0, atol=1e-10)
    assert (post >= 0).all()


def _fit_hmmlearn(X: np.ndarray, n_states: int = 5) -> GaussianHMM:
    m = GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=100,
        tol=1e-4,
        random_state=0,
    )
    m.fit(X)
    return m


def test_parity_with_hmmlearn():
    """Canonical NumPy forward filter must match hmmlearn's forward lattice
    (obtained via the private _hmmc.forward_log — NOT predict_proba, which
    is forward-backward SMOOTHING and leaks future data)."""
    from hmmlearn import _hmmc
    from scipy.special import logsumexp

    X = rng.normal(size=(400, 7))
    hmm = _fit_hmmlearn(X)
    flt = from_hmmlearn(hmm)
    ours = flt.posterior(X)

    log_frameprob = hmm._compute_log_likelihood(X)
    _, fwdlattice = _hmmc.forward_log(hmm.startprob_, hmm.transmat_, log_frameprob)
    forward_posterior = np.exp(fwdlattice - logsumexp(fwdlattice, axis=1, keepdims=True))
    forward_posterior = forward_posterior / forward_posterior.sum(axis=1, keepdims=True)
    assert np.abs(ours - forward_posterior).max() < 1e-10


def test_predict_proba_is_smoothed_not_causal():
    """Regression guard: hmmlearn predict_proba changes when FUTURE bars are
    appended (smoothed/forward-backward). The filtered posterior must not.
    This is why the pipeline never uses predict_proba."""
    X = rng.normal(size=(400, 7))
    hmm = _fit_hmmlearn(X)
    flt = from_hmmlearn(hmm)

    short = X[:200]
    post_short_filtered = flt.posterior(short)
    post_long_filtered = flt.posterior(X)
    np.testing.assert_allclose(post_short_filtered, post_long_filtered[:200], atol=1e-12)

    proba_short = hmm.predict_proba(short)
    proba_long = hmm.predict_proba(X)
    diff = np.abs(proba_short - proba_long[:200]).max()
    assert diff > 1e-6, f"predict_proba unexpectedly causal (diff={diff})"


def test_parity_loglikelihood():
    X = rng.normal(size=(400, 7))
    hmm = _fit_hmmlearn(X)
    flt = from_hmmlearn(hmm)
    assert abs(flt.score(X) - hmm.score(X)) < 1e-4


def test_from_hmmlearn_diag():
    X = rng.normal(size=(300, 7))
    hmm = _fit_hmmlearn(X)
    flt = from_hmmlearn(hmm)
    assert flt.var.shape == (5, 7)  # diag covars are (K, D)
    diag = np.diagonal(np.asarray(hmm.covars_), axis1=1, axis2=2)
    np.testing.assert_allclose(flt.var, diag)


def test_filtered_posterior_is_causal():
    """Posterior at t must not change when future bars are appended."""
    flt = _random_hmm()
    X = rng.normal(size=(400, 7))
    post_short = flt.posterior(X[:200])
    post_long = flt.posterior(X)
    np.testing.assert_allclose(post_short, post_long[:200], atol=1e-12)


def test_warmup_restart_equivalence():
    """Replaying the last W bars after a restart gives the same final
    posterior as the continuous run (float tolerance)."""
    flt = _random_hmm()
    X = rng.normal(size=(1000, 7))
    continuous = flt.posterior(X)
    warmup = flt.posterior(X[-500:])
    assert np.abs(continuous[-1] - warmup[-1]).max() < 1e-9
