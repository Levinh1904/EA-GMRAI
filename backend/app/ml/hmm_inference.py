"""Causal HMM inference — filtered posterior (forward algorithm) in pure NumPy.

This is the canonical inference engine used at runtime (and the reference for
a future MQL5/ONNX port). It implements the exact same recursion as hmmlearn's
forward pass with diagonal Gaussian emissions; parity is tested in
tests/test_hmm_inference.py (tol 1e-6).

Only the FORWARD (filtered) posterior is exposed — no Viterbi, no smoothing,
so the posterior at time t depends exclusively on observations <= t.
"""
from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

EPS = 1e-300


class HmmFilter:
    def __init__(
        self,
        startprob: np.ndarray,
        transmat: np.ndarray,
        means: np.ndarray,
        covars_diag: np.ndarray,
    ):
        self.startprob = np.asarray(startprob, dtype=np.float64)
        self.transmat = np.asarray(transmat, dtype=np.float64)
        self.means = np.asarray(means, dtype=np.float64)
        self.var = np.maximum(np.asarray(covars_diag, dtype=np.float64), EPS)
        self.n_states = self.means.shape[0]

        # Plain log-space convention, matching hmmlearn's _hmmc.forward_log:
        # zero probabilities are floored to EPS (log ~ -708, i.e. ~ -inf
        # mass). Parity with the hmmlearn forward lattice is tested to 1e-10.
        self._log_start = np.log(np.maximum(self.startprob, EPS))
        self._log_trans = np.log(np.maximum(self.transmat, EPS))
        self._log_norm = -0.5 * (self.means.shape[1] * np.log(2 * np.pi) + np.log(self.var).sum(axis=1))

    def log_emission(self, obs: np.ndarray) -> np.ndarray:
        """(T, D) -> (T, K) log emission probabilities."""
        obs = np.asarray(obs, dtype=np.float64)
        diff = obs[:, None, :] - self.means[None, :, :]
        quad = (diff * diff * (1.0 / self.var)[None, :, :]).sum(axis=2)
        return self._log_norm[None, :] - 0.5 * quad

    def forward_log(self, obs: np.ndarray) -> np.ndarray:
        """(T, D) -> (T, K) log-alpha; alpha_t uses only obs[0..t] (causal)."""
        log_em = self.log_emission(obs)
        t_max = obs.shape[0]
        alpha = np.empty((t_max, self.n_states))
        alpha[0] = self._log_start + log_em[0]
        for t in range(1, t_max):
            alpha[t] = logsumexp(alpha[t - 1][:, None] + self._log_trans, axis=0) + log_em[t]
        return alpha

    def posterior(self, obs: np.ndarray) -> np.ndarray:
        """(T, D) -> (T, K) filtered posterior P(state_t | obs[0..t])."""
        alpha = self.forward_log(obs)
        post = np.exp(alpha - logsumexp(alpha, axis=1, keepdims=True))
        return post / post.sum(axis=1, keepdims=True)

    def score(self, obs: np.ndarray) -> float:
        alpha = self.forward_log(obs)
        return float(logsumexp(alpha[-1]))


def from_hmmlearn(model) -> HmmFilter:
    """Build a canonical HmmFilter from a fitted hmmlearn GaussianHMM."""
    covars = np.asarray(model.covars_)
    if covars.ndim == 3:  # full covariance matrices
        covars = np.diagonal(covars, axis1=1, axis2=2)
    return HmmFilter(
        startprob=model.startprob_,
        transmat=model.transmat_,
        means=model.means_,
        covars_diag=covars,
    )
