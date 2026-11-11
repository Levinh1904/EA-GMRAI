"""Model registry state machine — transition guards."""
import pytest

from app.models import ModelVersion
from app.services.registry import ALLOWED_TRANSITIONS, set_version_status


def _mk(db, status="candidate"):
    from app.db import session

    with session() as s:
        v = ModelVersion(model_type="hmm", model_id=1, version=1, status=status,
                         metrics_json={"test_macro_f1": 0.6})
        s.add(v)
        s.commit()
        vid = v.id
    return vid


def test_archived_cannot_approve_without_restore(db):
    """archived -> approved bị chặn (khôi phục candidate trước) — đúng thiết kế."""
    from app.db import session
    from fastapi import HTTPException

    vid = _mk(db, "archived")
    with session() as s:
        v = s.get(ModelVersion, vid)
        with pytest.raises(HTTPException) as e:
            set_version_status(s, v, "approved", actor="test")
        assert "Cannot move from archived to approved" in str(e.value.detail)


def test_archived_to_candidate_allowed(db):
    from app.db import session

    vid = _mk(db, "archived")
    with session() as s:
        v = s.get(ModelVersion, vid)
        set_version_status(s, v, "candidate", actor="test")
        assert v.status == "candidate"


def test_candidate_to_approved_requires_metrics(db):
    from app.db import session
    from fastapi import HTTPException

    # metrics present -> OK
    vid = _mk(db, "candidate")
    with session() as s:
        v = s.get(ModelVersion, vid)
        set_version_status(s, v, "approved", actor="test")
        assert v.status == "approved"


def test_transition_table_shape():
    assert ALLOWED_TRANSITIONS["archived"] == {"candidate"}
    assert "approved" not in ALLOWED_TRANSITIONS["archived"]
    assert ALLOWED_TRANSITIONS["candidate"] == {"approved", "rejected"}
