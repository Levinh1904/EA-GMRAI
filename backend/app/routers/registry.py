from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import ModelVersion, User
from app.schemas import StatusChangeIn
from app.services.registry import artifact_exists, list_versions, set_version_status

registry_router = APIRouter(prefix="/models", tags=["registry"])


@registry_router.get("")
def list_models(
    model_type: str | None = Query(None, pattern="^(hmm|random_forest)$"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    versions = list_versions(db, model_type, limit)
    return {
        "models": [
            {
                "version_id": v.id,
                "model_type": v.model_type,
                "model_id": v.model_id,
                "version": v.version,
                "status": v.status,
                "metrics": v.metrics_json,
                "created_at": v.created_at.isoformat(),
                "has_artifact": artifact_exists(v),
            }
            for v in versions
        ]
    }


@registry_router.get("/{version_id}")
def get_model(
    version_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = db.get(ModelVersion, version_id)
    if v is None:
        raise HTTPException(404, "Model version not found")
    return {
        "version_id": v.id,
        "model_type": v.model_type,
        "model_id": v.model_id,
        "version": v.version,
        "status": v.status,
        "metrics": v.metrics_json,
        "artifact_path": v.artifact_path,
        "created_at": v.created_at.isoformat(),
    }


@registry_router.post("/{version_id}/status")
def change_status(
    version_id: int,
    body: StatusChangeIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    v = db.get(ModelVersion, version_id)
    if v is None:
        raise HTTPException(404, "Model version not found")
    v = set_version_status(db, v, body.status, actor=user.username, force=body.force)
    return {"version_id": v.id, "status": v.status}


@registry_router.get("/{version_id}/download")
def download_artifact(
    version_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    v = db.get(ModelVersion, version_id)
    if v is None or not v.artifact_path:
        raise HTTPException(404, "Artifact not found")
    path = Path(v.artifact_path)
    if not path.exists():
        raise HTTPException(410, "Artifact file missing on disk")
    return FileResponse(path, filename=path.name)
