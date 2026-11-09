"""RF labels + RF model: label mechanics, features, train/tune/proba."""
import numpy as np
import pandas as pd
import pytest

from app.ml.labels import make_labels
from app.ml.rf_model import (
    RF_FEATURE_NAMES,
    build_rf_features,
    predict_proba_rf,
    semantic_probs_array,
    train_rf,
    tune_rf,
)
from app.ml.synthetic import generate_synthetic_candles


def test_labels_last_horizon_nan():
    close = pd.Series(np.arange(1.0, 101.0), index=range(100))
    atr = pd.Series(0.5, index=range(100))
    labels = make_labels(close, atr_series=atr, horizon=12, up_threshold_atr=1.0)
    assert labels.iloc[-12:].isna().all()
    assert labels.iloc[:-12].notna().all()


def test_labels_direction():
    """Monotone up move must be TREND_UP; down move TREND_DOWN; flat SIDEWAYS."""
    n = 100
    idx = range(n)
    close = pd.Series(2400.0 * 1.02 ** np.arange(n), index=idx)  # +2%/bar geometric
    atr = pd.Series(30.0, index=idx)
    labels = make_labels(close, atr_series=atr, horizon=12, up_threshold_atr=1.0)
    assert (labels.iloc[: n - 12] == "TREND_UP").all()

    close = pd.Series(2400.0 * 0.98 ** np.arange(n), index=idx)  # -2%/bar geometric
    labels = make_labels(close, atr_series=atr, horizon=12, up_threshold_atr=1.0)
    assert (labels.iloc[: n - 12] == "TREND_DOWN").all()

    close = pd.Series(np.full(n, 2400.0), index=idx)
    labels = make_labels(close, atr_series=atr, horizon=12, up_threshold_atr=1.0)
    assert (labels.iloc[: n - 12] == "SIDEWAYS").all()


def test_rf_feature_matrix():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=800, seed=3)
    from app.ml.features import build_features

    feats = build_features(df_m5, df_m15, df_h1)
    rng = np.random.default_rng(0)
    posterior = rng.dirichlet(np.ones(5), size=len(feats))
    transmat = rng.dirichlet(np.ones(5), size=5)
    mapping = {
        "0": {"regime": "SIDEWAYS", "reason": "x", "evidence": {}},
        "1": {"regime": "TREND_UP", "reason": "x", "evidence": {}},
        "2": {"regime": "TREND_DOWN", "reason": "x", "evidence": {}},
        "3": {"regime": "TRANSITION", "reason": "x", "evidence": {}},
        "4": {"regime": "HIGH_VOLATILITY", "reason": "x", "evidence": {}},
    }
    semantic = semantic_probs_array(posterior, mapping)
    X = build_rf_features(posterior, transmat, mapping, feats, semantic)
    assert list(X.columns) == RF_FEATURE_NAMES
    assert len(X) == len(feats)
    assert np.isfinite(X.values).all()


def test_train_tune_proba():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=800, seed=5)
    from app.ml.features import build_features
    from app.ml.indicators import atr
    from app.ml.labels import make_labels

    feats = build_features(df_m5, df_m15, df_h1)
    close = df_m15["close"].reindex(feats.index)
    labels = make_labels(close, atr_series=atr(df_m15, 14).reindex(feats.index), horizon=12, up_threshold_atr=1.0)
    labels = labels.dropna()
    n = len(labels)
    rng = np.random.default_rng(1)
    posterior = rng.dirichlet(np.ones(5), size=len(feats))
    mapping = {
        str(i): {"regime": r, "reason": "x", "evidence": {}}
        for i, r in enumerate(["SIDEWAYS", "TREND_UP", "TREND_DOWN", "TRANSITION", "HIGH_VOLATILITY"])
    }
    semantic = semantic_probs_array(posterior, mapping)
    X = build_rf_features(posterior, rng.dirichlet(np.ones(5), size=5), mapping, feats, semantic).iloc[:n]

    cut = int(n * 0.7)
    model, params, f1 = tune_rf(X.iloc[:cut], labels.iloc[:cut], X.iloc[cut:], labels.iloc[cut:])
    assert params, "tune must pick params"
    assert 0.0 <= f1 <= 1.0

    model2 = train_rf(X.iloc[:cut], labels.iloc[:cut], {"n_estimators": 50, "max_depth": 6})
    probs = predict_proba_rf(model2, X.iloc[cut:])
    assert list(probs.columns) == ["TREND_DOWN", "SIDEWAYS", "TREND_UP"]
    np.testing.assert_allclose(probs.values.sum(axis=1), 1.0, atol=1e-6)
