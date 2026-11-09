"""ONNX export for the Random Forest + parity checking.

HMM is NOT exported to ONNX (GaussianHMM forward filtering is not supported
by skl2onnx); the canonical NumPy HmmFilter (ml/hmm_inference.py) is the
portable reference engine, parity-tested against hmmlearn.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from skl2onnx import to_onnx
from skl2onnx.common.data_types import FloatTensorType

PARITY_TOLERANCE = 1e-5


def export_rf_onnx(model, feature_names: list[str], out_path: Path, opset: int = 15) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    initial_types = [("float_input", FloatTensorType([None, len(feature_names)]))]
    onx = to_onnx(
        model,
        initial_types=initial_types,
        options={id(model): {"zipmap": False}},
        target_opset=opset,
    )
    onnx.save_model(onx, str(out_path))
    return out_path


def run_onnx_proba(path: Path, X: np.ndarray):
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    feed = {"float_input": X.astype(np.float32)}
    return sess.run(None, feed)


def parity_check(model, X: np.ndarray, onnx_path: Path, tol: float = PARITY_TOLERANCE) -> dict:
    """Compare sklearn vs ONNX class probabilities."""
    sk_probs = np.asarray(model.predict_proba(X), dtype=np.float64)
    onnx_out = run_onnx_proba(onnx_path, X)
    label_idx, prob_idx = None, None
    for i, out in enumerate(onnx_out):
        if out.ndim == 2 and out.shape[1] == len(model.classes_):
            prob_idx = i
        if out.ndim == 1 and len(out) == len(X):
            label_idx = i
    if prob_idx is None:
        raise RuntimeError(f"Could not locate probability output in ONNX model (outputs: {[o.shape for o in onnx_out]})")
    onnx_probs = np.asarray(onnx_out[prob_idx], dtype=np.float64)
    max_abs = float(np.abs(sk_probs - onnx_probs).max())
    return {
        "max_abs_diff": max_abs,
        "passed": max_abs <= tol,
        "tolerance": tol,
        "n_samples": int(len(X)),
        "classes": [str(c) for c in model.classes_],
    }
