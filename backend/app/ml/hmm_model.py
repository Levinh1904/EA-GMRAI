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


def _direction_score(
    st: dict,
    z: float,
    trend_z_threshold: float,
    slope_scale: float,
    di_scale: float,
    adx_floor: float,
) -> float:
    """Signed direction evidence in [-1, 1]: +up, -down.

    The old mapping required ``|z| >= trend_z_threshold`` on the per-bar
    return drift alone. A state that spans a whole trend often has a small
    ``ret1_mean`` relative to its own std (up-moves and pullbacks cancel), so
    genuine trend states were being rejected as UNKNOWN — the HMM never
    produced TREND_UP at all.

    This blends three independent directional signals, each squashed to
    [-1, 1] and weighted, then gates the result by ADX so a low-ADX state can
    never be labelled a trend no matter how large one component looks:

        slope  = tanh(ema_slope_mean / slope_scale)     (already ATR-normalised)
        di     = tanh(di_gap_mean   / di_scale)         (+DI - -DI, /100 units)
        drift  = tanh(z / trend_z_threshold)            (return drift in its own sd)

        direction = (0.35*slope + 0.30*di + 0.35*drift) * gate
        gate      = min(adx_mean / adx_floor, 1.0)
    """
    slope = st.get("ema_slope_mean")
    di = st.get("di_gap_mean")
    adx = st.get("adx_mean")
    if slope is None or di is None or adx is None:
        return 0.0
    slope_s = float(np.tanh(slope / slope_scale))
    di_s = float(np.tanh(di / di_scale))
    drift_s = float(np.tanh(z / max(trend_z_threshold, 1e-6)))
    gate = float(min(max(adx / max(adx_floor, 1e-6), 0.0), 1.0))
    return (0.35 * slope_s + 0.30 * di_s + 0.35 * drift_s) * gate


def map_states(
    stats: dict,
    n_states: int,
    vol_ratio_threshold: float = 1.25,
    trend_z_threshold: float = 0.30,
    adx_sideways_max: float = 0.25,
    duration_transition_max: float = 4.0,
    direction_threshold: float = 0.35,
    slope_scale: float = 0.5,
    di_scale: float = 0.10,
) -> dict:
    """Map hidden states to semantic regimes using train-set statistics only.

    Never forces a classification: conflicting/weak evidence -> UNKNOWN.
    Trend direction is decided by a composite directional score (see
    `_direction_score`) rather than the return drift alone, so directional
    states with modest mean returns are still recognised.
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
        direction = _direction_score(
            st, z, trend_z_threshold, slope_scale, di_scale, adx_sideways_max
        )
        if is_high_vol:
            mapping[str(s)] = {"regime": "HIGH_VOLATILITY", "reason": "atr_ratio_outlier", "evidence": st}
        elif direction >= direction_threshold:
            mapping[str(s)] = {
                "regime": "TREND_UP",
                "reason": "directional_score_up",
                "direction_score": round(direction, 4),
                "evidence": st,
            }
        elif direction <= -direction_threshold:
            mapping[str(s)] = {
                "regime": "TREND_DOWN",
                "reason": "directional_score_down",
                "direction_score": round(direction, 4),
                "evidence": st,
            }
        elif abs(z) < trend_z_threshold and st["adx_mean"] < adx_sideways_max:
            mapping[str(s)] = {
                "regime": "SIDEWAYS",
                "reason": "low_return_low_adx",
                "direction_score": round(direction, 4),
                "evidence": st,
            }
        elif st["duration_mean"] is not None and st["duration_mean"] <= duration_transition_max:
            mapping[str(s)] = {
                "regime": "TRANSITION",
                "reason": "short_duration",
                "direction_score": round(direction, 4),
                "evidence": st,
            }
        else:
            mapping[str(s)] = {
                "regime": "UNKNOWN",
                "reason": "ambiguous_evidence",
                "direction_score": round(direction, 4),
                "evidence": st,
            }
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
