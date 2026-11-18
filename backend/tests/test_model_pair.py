"""Registry pairing: never mix an HMM from one training run with another RF."""
from app.db import session
from app.models import ModelVersion
from app.services.registry import get_active_approved_pair
from app.timeutil import utcnow


def _version(model_type: str, model_id: int, status: str = "approved") -> ModelVersion:
    return ModelVersion(
        model_type=model_type,
        model_id=model_id,
        version=1,
        status=status,
        created_at=utcnow(),
    )


def test_pairing_uses_same_model_id(db):
    s = session()
    # Newest HMM is model_id 3, but there is no RF model_id 3 yet.
    s.add(_version("hmm", 1))
    s.add(_version("random_forest", 1))
    s.add(_version("hmm", 3))
    s.add(_version("random_forest", 2))
    s.commit()
    assert get_active_approved_pair(s) == (s.query(ModelVersion).filter_by(model_type="hmm", model_id=1).one(),
                                           s.query(ModelVersion).filter_by(model_type="random_forest", model_id=1).one())

    s.add(_version("random_forest", 3))
    s.commit()
    pair = get_active_approved_pair(s)
    assert pair is not None
    assert pair[0].model_id == pair[1].model_id == 3


def test_pairing_ignores_non_approved(db):
    s = session()
    s.add(_version("hmm", 2, "archived"))
    s.add(_version("random_forest", 2, "candidate"))
    s.commit()
    assert get_active_approved_pair(s) is None
