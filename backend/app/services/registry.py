"""Model registry helpers: versions, status transitions, active models."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.models import HmmModel, ModelVersion, RandomForestModel, SystemLog
from app.timeutil import utcnow

VALID_STATUSES = {"training", "validating", "candidate", "approved", "rejected", "archived"}
ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "rejected"},
    "approved": {"archived"},
    "rejected": {"archived", "candidate"},
    "archived": {"candidate"},  # khôi phục để đánh giá lại — không bao giờ approved trực tiếp
    "training": {"validating", "candidate", "rejected"},
    "validating": {"candidate", "rejected"},
}


def set_version_status(
    db: Session,
    version: ModelVersion,
    new_status: str,
    actor: str = "admin",
    force: bool = False,
) -> ModelVersion:
    if new_status not in VALID_STATUSES:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid status: {new_status}")
    if not force and new_status not in ALLOWED_TRANSITIONS.get(version.status, set()):
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            f"Cannot move from {version.status} to {new_status}",
        )
    if new_status == "approved" and not force:
        m = version.metrics_json or {}
        if "test_macro_f1" not in m and "val_loglik" not in m:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Approval requires validation/test metrics on the version",
            )
    version.status = new_status
    db.add(
        SystemLog(
            level="INFO",
            component="registry",
            message=f"model_version {version.id} ({version.model_type}) -> {new_status}",
            meta_json={"actor": actor},
        )
    )
    db.commit()
    return version


def list_versions(db: Session, model_type: str | None = None, limit: int = 100):
    q = db.query(ModelVersion)
    if model_type:
        q = q.filter(ModelVersion.model_type == model_type)
    return q.order_by(ModelVersion.id.desc()).limit(limit).all()


def get_active_approved(db: Session, model_type: str) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == model_type, ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .first()
    )


def get_active_approved_pair(db: Session) -> tuple[ModelVersion, ModelVersion] | None:
    """Newest approved HMM+RF that belong to the same training pair.

    `model_id` is the id in the HMM/RF table; training creates both rows with the
    same model_id, so pairing on it prevents mixing an old HMM with a new RF
    (which silently produces confident garbage because the 5-state layout is the
    same but the state semantics are not).
    """
    hmms = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == "hmm", ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .all()
    )
    rfs = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_type == "random_forest", ModelVersion.status == "approved")
        .order_by(ModelVersion.id.desc())
        .all()
    )
    for h in hmms:
        for r in rfs:
            if h.model_id == r.model_id:
                return h, r
    return None


def artifact_exists(version: ModelVersion) -> bool:
    return bool(version.artifact_path) and Path(version.artifact_path).exists()
