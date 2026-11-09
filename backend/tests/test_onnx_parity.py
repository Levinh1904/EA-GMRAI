"""ONNX export + parity between sklearn and onnxruntime."""
import numpy as np
import pytest

from app.ml.features import build_features
from app.ml.labels import make_labels
from app.ml.onnx_export import PARITY_TOLERANCE, export_rf_onnx, parity_check, run_onnx_proba
from app.ml.rf_model import RF_FEATURE_NAMES, build_rf_features, semantic_probs_array, train_rf
from app.ml.synthetic import generate_synthetic_candles


@pytest.fixture(scope="module")
def rf_setup():
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=1200, seed=21)
    from app.ml.indicators import atr

    feats = build_features(df_m5, df_m15, df_h1)
    close = df_m15["close"].reindex(feats.index)
    labels = make_labels(close, atr_series=atr(df_m15, 14).reindex(feats.index), horizon=12, up_threshold_atr=1.0).dropna()
    n = len(labels)
    rng = np.random.default_rng(0)
    posterior = rng.dirichlet(np.ones(5), size=len(feats))
    mapping = {
        str(i): {"regime": r, "reason": "x", "evidence": {}}
        for i, r in enumerate(["SIDEWAYS", "TREND_UP", "TREND_DOWN", "TRANSITION", "HIGH_VOLATILITY"])
    }
    semantic = semantic_probs_array(posterior, mapping)
    X = build_rf_features(posterior, rng.dirichlet(np.ones(5), size=5), mapping, feats, semantic).iloc[:n]
    model = train_rf(X.iloc[: int(n * 0.7)], labels.iloc[: int(n * 0.7)], {"n_estimators": 60, "max_depth": 8})
    return model, X.iloc[int(n * 0.7) :]


def test_export_and_parity(rf_setup, tmp_path):
    model, X_test = rf_setup
    out = tmp_path / "model.onnx"
    export_rf_onnx(model, RF_FEATURE_NAMES, out)
    assert out.exists()
    res = parity_check(model, X_test.values, out, tol=PARITY_TOLERANCE)
    assert res["passed"], res
    assert res["max_abs_diff"] <= PARITY_TOLERANCE


def test_onnx_runtime_outputs(rf_setup, tmp_path):
    model, X_test = rf_setup
    out = tmp_path / "model.onnx"
    export_rf_onnx(model, RF_FEATURE_NAMES, out)
    outs = run_onnx_proba(out, X_test.values[:20])
    probs = [o for o in outs if o.ndim == 2 and o.shape[1] == 3][0]
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)
    assert (probs >= 0).all() and (probs <= 1).all()
