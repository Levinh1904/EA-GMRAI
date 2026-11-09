"""Gaussian HMM training, state statistics and semantic mapping.

Hidden states have NO fixed meaning — each state is characterized with
statistics computed on the TRAIN set only, then mapped to a semantic regime.
States without sufficient evidence are marked UNKNOWN (never forced).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

from app.ml.hmm_inference import HmmFilter, from_hmmlearn

REGIME_NAMES = ["SIDEWAYS", "TREND_UP", "TREND_DOWN", "TRANSITION", "HIGH_VOLATILITY"]


def train_hmm(
    X: np.ndarray,
    n_states: int = 5,
    n_init: int = 10,
    seed: int = 42,
    n_iter: int = 200,
    tol: float = 1e-4,
) -> tuple[GaussianHMM, float]:
    """Multi-start training; returns best model (by train log-likelihood)."""
    best_model, best_score = None, -np.inf
    rng = np.random.default_rng(seed)
    seeds = rng.integers(0, 2**31 - 1, size=n_init)
    for s in seeds:
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=n_iter,
            tol=tol,
            random_state=int(s),
            init_params="stmc",
            params="stmc",
        )
        model.fit(X)
        try:
            score = model.score(X)
        except Exception:  # degenerate fit — skip
            continue
        if score > best_score:
            best_model, best_score = model, float(score)
    if best_model is None:
        raise RuntimeError("HMM training failed for all initializations")
    return best_model, best_score


def extract_params(model: GaussianHMM) -> dict:
    return {
        "startprob": np.asarray(model.startprob_).tolist(),
        "transmat": np.asarray(model.transmat_).tolist(),
        "means": np.asarray(model.means_).tolist(),
        "covars_diag": np.diagonal(np.asarray(model.covars_), axis1=1, axis2=2).tolist(),
    }


def state_statistics(
    feature_df: pd.DataFrame,
    posterior: np.ndarray,
    n_states: int,
    ret_col: str = "ret1",
    adx_col: str = "adx_norm",
    slope_col: str = "ema_slope",
    eff_col: str = "efficiency_ratio",
    atr_col: str = "atr_ratio",
    di_col: str = "di_gap",
) -> dict:
    """Per-state descriptive statistics from filtered (causal) decoding."""
    if len(feature_df) != len(posterior):
        raise ValueError("feature_df and posterior length mismatch")
    states = posterior.argmax(axis=1)
    stats = {}
    for s in range(n_states):
        mask = states == s
        n = int(mask.sum())
        if n == 0:
            stats[str(s)] = {
                "n_obs": 0,
                "occupancy": 0.0,
                "ret1_mean": None,
                "ret1_std": None,
                "adx_mean": None,
                "ema_slope_mean": None,
                "efficiency_mean": None,
                "atr_ratio_mean": None,
                "di_gap_mean": None,
                "duration_mean": None,
                "evidence": "no_observations",
            }
            continue
        runs = _run_lengths(states == s)
        stats[str(s)] = {
            "n_obs": n,
            "occupancy": round(n / len(feature_df), 4),
            "ret1_mean": round(float(feature_df[ret_col][mask].mean()), 6),
            "ret1_std": round(float(feature_df[ret_col][mask].std()), 6),
            "adx_mean": round(float(feature_df[adx_col][mask].mean()), 6),
            "ema_slope_mean": round(float(feature_df[slope_col][mask].mean()), 6),
            "efficiency_mean": round(float(feature_df[eff_col][mask].mean()), 6),
            "atr_ratio_mean": round(float(feature_df[atr_col][mask].mean()), 6),
            "di_gap_mean": round(float(feature_df[di_col][mask].mean()), 6),
            "duration_mean": round(float(np.mean(runs)), 2) if runs else None,
            "evidence": "ok",
        }
    return stats


def _run_lengths(bool_arr: np.ndarray) -> list[int]:
    runs: list[int] = []
    count = 0
    for v in bool_arr:
        if v:
            count += 1
        else:
            if count > 0:
                runs.append(count)
            count = 0
    if count > 0:
        runs.append(count)
    return runs


def map_states(
    stats: dict,
    n_states: int,
    vol_ratio_threshold: float = 1.25,
    trend_z_threshold: float = 0.30,
    adx_sideways_max: float = 0.25,
    duration_transition_max: float = 4.0,
) -> dict:
    """Map hidden states to semantic regimes using train-set statistics only.

    Never forces a classification: conflicting/weak evidence -> UNKNOWN.
    """
    mapping: dict = {}
    atr_means = [stats[str(s)]["atr_ratio_mean"] or 0.0 for s in range(n_states)]
    vol_median = float(np.median([a for a in atr_means if a > 0]) or 1.0)

    for s in range(n_states):
        st = stats[str(s)]
        if st["n_obs"] == 0:
            mapping[str(s)] = {"regime": "UNKNOWN", "reason": "no_observations", "evidence": st}
            continue
        z = st["ret1_mean"] / max(st["ret1_std"], 1e-6)
        is_high_vol = st["atr_ratio_mean"] >= vol_ratio_threshold * vol_median and st["atr_ratio_mean"] > 1.05
        if is_high_vol:
            mapping[str(s)] = {"regime": "HIGH_VOLATILITY", "reason": "atr_ratio_outlier", "evidence": st}
        elif abs(z) < trend_z_threshold and st["adx_mean"] < adx_sideways_max:
            mapping[str(s)] = {"regime": "SIDEWAYS", "reason": "low_return_low_adx", "evidence": st}
        elif z >= trend_z_threshold and (st["ema_slope_mean"] > 0 or st["di_gap_mean"] > 0):
            mapping[str(s)] = {"regime": "TREND_UP", "reason": "positive_return_drift", "evidence": st}
        elif z <= -trend_z_threshold and (st["ema_slope_mean"] < 0 or st["di_gap_mean"] < 0):
            mapping[str(s)] = {"regime": "TREND_DOWN", "reason": "negative_return_drift", "evidence": st}
        elif st["duration_mean"] is not None and st["duration_mean"] <= duration_transition_max:
            mapping[str(s)] = {"regime": "TRANSITION", "reason": "short_duration", "evidence": st}
        else:
            mapping[str(s)] = {"regime": "UNKNOWN", "reason": "ambiguous_evidence", "evidence": st}
    return mapping


def semantic_probabilities(posterior_row: np.ndarray, mapping: dict) -> dict:
    """Aggregate posterior mass per semantic regime from one posterior row."""
    probs = {}
    for s, m in mapping.items():
        regime = m["regime"]
        probs[regime] = probs.get(regime, 0.0) + float(posterior_row[int(s)])
    return probs


def save_hmm_artifact(
    path: Path,
    params: dict,
    scaler_mean: list,
    scaler_std: list,
    feature_columns: list[str],
    state_mapping: dict,
    meta: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model_type": "gaussian_hmm",
        "params": params,
        "scaler_mean": scaler_mean,
        "scaler_std": scaler_std,
        "feature_columns": feature_columns,
        "state_mapping": state_mapping,
        "meta": meta,
    }
    path.write_text(json.dumps(artifact, indent=2))


def load_hmm_artifact(path: Path) -> dict:
    return json.loads(path.read_text())


def hmm_filter_from_artifact(artifact: dict) -> HmmFilter:
    p = artifact["params"]
    return HmmFilter(
        startprob=np.array(p["startprob"]),
        transmat=np.array(p["transmat"]),
        means=np.array(p["means"]),
        covars_diag=np.array(p["covars_diag"]),
    )


def filtered_posterior(model: GaussianHMM, X: np.ndarray) -> np.ndarray:
    """Filtered (CAUSAL) posterior via the canonical NumPy forward filter.

    IMPORTANT: hmmlearn's predict_proba() returns SMOOTHED posteriors
    (forward-backward, uses future observations) — using it for historical
    signals is a lookahead leak. Never call it in the pipeline.
    """
    return from_hmmlearn(model).posterior(X)


def posterior_from_filter(hmm_filter: HmmFilter, X: np.ndarray) -> np.ndarray:
    return hmm_filter.posterior(X)
