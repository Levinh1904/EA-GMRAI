"""Random Forest regime classifier.

RF receives HMM outputs (filtered posterior, state, transition info) as
FEATURES — the two models are not combined by naively multiplying
probabilities. The ensemble choice is validated out-of-sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, f1_score

from app.ml.features import ALL_FEATURES
from app.ml.hmm_model import semantic_probabilities
from app.ml.labels import LABEL_CLASSES

POSTERIOR_COLS = [f"hmm_p{i}" for i in range(5)]
STATE_COLS = [f"hmm_state{i}" for i in range(5)]
DERIVED_COLS = [
    "hmm_entropy",
    "trans_to_up",
    "trans_to_down",
    "delta_up_1",
    "delta_up_3",
]
RF_FEATURE_NAMES = POSTERIOR_COLS + STATE_COLS + DERIVED_COLS + ALL_FEATURES

DEFAULT_PARAMS = {
    "n_estimators": 300,
    "min_samples_leaf": 15,
    "max_depth": None,
    "class_weight": "balanced_subsample",
    "n_jobs": -1,
    "random_state": 42,
}

TUNE_GRID = [
    {"max_depth": None, "min_samples_leaf": 5},
    {"max_depth": None, "min_samples_leaf": 15},
    {"max_depth": None, "min_samples_leaf": 30},
    {"max_depth": 8, "min_samples_leaf": 15},
    {"max_depth": 12, "min_samples_leaf": 15},
]


def semantic_probs_array(posterior: np.ndarray, mapping: dict) -> pd.DataFrame:
    """(T,K) posterior + mapping -> DataFrame of per-regime probabilities per bar."""
    rows = [semantic_probabilities(p, mapping) for p in posterior]
    return pd.DataFrame(rows).fillna(0.0)


def build_rf_features(
    posterior: np.ndarray,
    transmat: np.ndarray,
    mapping: dict,
    feature_df: pd.DataFrame,
    semantic_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the full RF feature matrix (causal — posterior is filtered)."""
    T = posterior.shape[0]
    up_states = [int(s) for s, m in mapping.items() if m["regime"] == "TREND_UP"]
    down_states = [int(s) for s, m in mapping.items() if m["regime"] == "TREND_DOWN"]
    trans_up_col = transmat[:, up_states].sum(axis=1) if up_states else np.zeros(posterior.shape[1])
    trans_down_col = transmat[:, down_states].sum(axis=1) if down_states else np.zeros(posterior.shape[1])

    out = pd.DataFrame(index=feature_df.index)
    out[POSTERIOR_COLS] = posterior
    states = posterior.argmax(axis=1)
    for i in range(posterior.shape[1]):
        out[f"hmm_state{i}"] = (states == i).astype(float)
    p = np.maximum(posterior, 1e-12)
    out["hmm_entropy"] = -(p * np.log(p)).sum(axis=1)
    out["trans_to_up"] = posterior @ trans_up_col
    out["trans_to_down"] = posterior @ trans_down_col
    if "TREND_UP" in semantic_df.columns:
        up = semantic_df["TREND_UP"]
        out["delta_up_1"] = up.diff(1).fillna(0.0).to_numpy()
        out["delta_up_3"] = up.diff(3).fillna(0.0).to_numpy()
    else:
        out["delta_up_1"] = 0.0
        out["delta_up_3"] = 0.0
    out[ALL_FEATURES] = feature_df[ALL_FEATURES]
    assert len(out) == T
    return out[RF_FEATURE_NAMES]


def train_rf(X: pd.DataFrame, y: pd.Series, params: dict | None = None) -> RandomForestClassifier:
    p = {**DEFAULT_PARAMS, **(params or {})}
    p = {k: v for k, v in p.items() if v is not None}
    model = RandomForestClassifier(**p)
    model.fit(X.values, y.values)
    return model


def tune_rf(
    X_subtrain: pd.DataFrame,
    y_subtrain: pd.Series,
    X_subval: pd.DataFrame,
    y_subval: pd.Series,
) -> tuple[RandomForestClassifier, dict, float]:
    """Small grid tuned on the time-ordered validation slice (macro F1)."""
    best_model, best_params, best_score = None, None, -1.0
    for g in TUNE_GRID:
        m = train_rf(X_subtrain, y_subtrain, g)
        pred = m.predict(X_subval.values)
        score = f1_score(y_subval, pred, labels=LABEL_CLASSES, average="macro", zero_division=0)
        if score > best_score:
            best_model, best_params, best_score = m, dict(g), float(score)
    return best_model, best_params, best_score


def maybe_calibrate(
    model: RandomForestClassifier,
    X_subval: pd.DataFrame,
    y_subval: pd.Series,
) -> tuple[RandomForestClassifier, dict]:
    """Calibrate with isotonic regression only if it improves Brier score on subval."""
    y_oh = pd.get_dummies(y_subval)[LABEL_CLASSES].values
    try:
        probs_raw = model.predict_proba(X_subval.values)
        raw_classes = list(model.classes_)
        raw_probs = np.zeros_like(y_oh)
        for i, c in enumerate(raw_classes):
            if c in LABEL_CLASSES:
                raw_probs[:, LABEL_CLASSES.index(c)] = probs_raw[:, i]
        raw_brier = float(np.mean((raw_probs - y_oh) ** 2))

        cal = CalibratedClassifierCV(estimator=model, method="isotonic", cv=3)
        cal.fit(X_subval.values, y_subval.values)
        probs_cal = cal.predict_proba(X_subval.values)
        cal_classes = list(cal.classes_)
        cal_probs = np.zeros_like(y_oh)
        for i, c in enumerate(cal_classes):
            if c in LABEL_CLASSES:
                cal_probs[:, LABEL_CLASSES.index(c)] = probs_cal[:, i]
        cal_brier = float(np.mean((cal_probs - y_oh) ** 2))
    except Exception:
        return model, {"applied": False, "reason": "calibration_failed"}

    if cal_brier < raw_brier:
        return cal, {"applied": True, "brier_before": raw_brier, "brier_after": cal_brier}
    return model, {"applied": False, "brier_before": raw_brier, "brier_after": cal_brier}


def predict_proba_rf(model: RandomForestClassifier, X: pd.DataFrame) -> pd.DataFrame:
    """Predict class probabilities aligned to LABEL_CLASSES order."""
    probs = model.predict_proba(X.values)
    out = pd.DataFrame(0.0, index=X.index, columns=LABEL_CLASSES)
    for i, c in enumerate(model.classes_):
        if c in LABEL_CLASSES:
            out[c] = probs[:, i]
    return out
