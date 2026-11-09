from pathlib import Path

import joblib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.ml.onnx_export import export_rf_onnx, parity_check
from app.ml.rf_model import RF_FEATURE_NAMES
from app.models import ModelVersion, User

onnx_router = APIRouter(prefix="/models", tags=["onnx"])


@onnx_router.post("/{version_id}/export-onnx")
def export_onnx(
    version_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    v = db.get(ModelVersion, version_id)
    if v is None or v.model_type != "random_forest":
        raise HTTPException(404, "Random forest version not found")
    if not v.artifact_path:
        raise HTTPException(404, "Artifact missing")
    artifact = Path(v.artifact_path)
    if not artifact.exists():
        raise HTTPException(410, "Artifact file missing on disk")
    model = joblib.load(artifact)
    out_path = artifact.parent / "model.onnx"
    export_rf_onnx(model, RF_FEATURE_NAMES, out_path)
    # Quick parity check with a dummy zero-ish sample (documented tolerance).
    import numpy as np

    parity = parity_check(model, np.zeros((1, len(RF_FEATURE_NAMES)), dtype=np.float64), out_path)
    v.artifact_path = str(artifact)
    db.commit()
    return {"onnx_path": str(out_path), "parity": parity}


@onnx_router.get("/{version_id}/onnx")
def download_onnx(
    version_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = db.get(ModelVersion, version_id)
    if v is None:
        raise HTTPException(404, "Version not found")
    if v.model_type != "random_forest" or not v.artifact_path:
        raise HTTPException(404, "ONNX only available for random_forest models")
    onnx_path = Path(v.artifact_path).parent / "model.onnx"
    if not onnx_path.exists():
        raise HTTPException(410, "ONNX file not exported yet")
    return FileResponse(onnx_path, filename="model.onnx")
