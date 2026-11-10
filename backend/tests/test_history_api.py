"""History module API tests — full job + endpoints + exports."""
import io

import pytest
from fastapi.testclient import TestClient

from app.ml.history import HistoryConfig
from app.models import ModelVersion, RegimeHistoryRun
from app.services.history import run_history_job
from app.services.registry import set_version_status
from app.services.training import TrainingConfig, run_training


@pytest.fixture(scope="module")
def history_setup(tmp_path_factory):
    """Isolated file DB: train tiny models, approve, run a history job."""
    from app.db import Base, get_engine, init_engine, reset_engine, session
    from tests.test_training_pipeline import _seed_synthetic

    reset_engine()
    db_path = tmp_path_factory.mktemp("hist") / "hist.db"
    init_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(get_engine())

    with session() as s:
        _seed_synthetic(s, n_m15=2200)
        summary = run_training(
            s, TrainingConfig(hmm_n_states=5, hmm_n_init=3, seed=42, train_frac=0.6, val_frac=0.2)
        )
        hmm_v = s.get(ModelVersion, summary["hmm_version_id"])
        rf_v = s.get(ModelVersion, summary["rf_version_id"])
        set_version_status(s, hmm_v, "approved", force=True)
        set_version_status(s, rf_v, "approved", force=True)
        run_row = RegimeHistoryRun(
            symbol="XAUUSD", timeframe="M15", status="pending",
            config_json=HistoryConfig().to_dict(),
        )
        s.add(run_row)
        s.commit()
        run_id = run_row.id
    with session() as s:
        result = run_history_job(s, run_id, HistoryConfig())
    reset_engine()
    return str(db_path), run_id, result


@pytest.fixture()
def hist_client(history_setup):
    """Client bound to the module's history DB (bootstrap seeds admin)."""
    from app.db import init_engine, reset_engine

    db_path, _, _ = history_setup
    reset_engine()
    init_engine(f"sqlite:///{db_path}")
    from app.main import app

    with TestClient(app) as c:
        yield c
    reset_engine()


@pytest.fixture()
def hist_token(hist_client):
    r = hist_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-change-me"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_history_job_done(history_setup):
    _, run_id, result = history_setup
    assert result["status"] == "done"
    assert result["bar_count"] >= 1500
    assert result["segment_count"] >= 5
    assert result["data_source"] == "synthetic_demo"


def test_history_api_endpoints(hist_client, hist_token, history_setup):
    _, run_id, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}
    base = "/api/v1/history"

    r = hist_client.get(f"{base}/runs", headers=h)
    assert r.status_code == 200 and len(r.json()["runs"]) >= 1

    r = hist_client.get(f"{base}/runs/{run_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "done"

    r = hist_client.get(f"{base}/runs/{run_id}/bars?limit=100", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1500 and len(body["bars"]) == 100
    assert "regime" in body["bars"][0] and "hmm_posterior" in body["bars"][0]

    r = hist_client.get(f"{base}/runs/{run_id}/segments?limit=50", headers=h)
    assert r.status_code == 200
    segs = r.json()["segments"]
    assert len(segs) >= 5
    seg_id = segs[0]["id"]
    assert all(k in segs[0] for k in ("duration_minutes", "mfe", "mae", "hmm_probs"))

    r = hist_client.get(f"{base}/runs/{run_id}/segments/{seg_id}", headers=h)
    assert r.status_code == 200

    # filters
    r = hist_client.get(f"{base}/runs/{run_id}/segments?min_duration=15&max_duration=100000&limit=500", headers=h)
    assert r.status_code == 200

    for stat in ("duration", "trends", "sideways", "early_trend", "transitions", "multi_tf"):
        r = hist_client.get(f"{base}/runs/{run_id}/stats/{stat}", headers=h)
        assert r.status_code == 200, f"{stat}: {r.text[:200]}"
    r = hist_client.get(f"{base}/runs/{run_id}/stats/periods?period=week", headers=h)
    assert r.status_code == 200 and len(r.json()["rows"]) >= 1
    r = hist_client.get(f"{base}/runs/{run_id}/compare?vs_reference=true", headers=h)
    assert r.status_code == 200
    assert "classification" in r.json()


def test_history_exports(hist_client, hist_token, history_setup):
    _, run_id, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}

    r = hist_client.get(f"/api/v1/history/runs/{run_id}/export?format=csv&scope=segments", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "regime" in r.text

    r = hist_client.get(f"/api/v1/history/runs/{run_id}/export?format=csv&scope=bars", headers=h)
    assert r.status_code == 200

    r = hist_client.get(f"/api/v1/history/runs/{run_id}/export?format=xlsx&scope=segments", headers=h)
    assert r.status_code == 200
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["segments"]
    assert ws.max_row > 10

    r = hist_client.get(f"/api/v1/history/runs/{run_id}/export?format=pdf&scope=report", headers=h)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_history_requires_admin_to_run(hist_client, hist_token):
    from app.db import session as new_session

    with new_session() as s:
        from app.models import User
        from app.security.auth import hash_password

        if not s.query(User).filter(User.username == "analyst2").first():
            s.add(User(username="analyst2", hashed_password=hash_password("x"), role="analyst"))
            s.commit()
    r = hist_client.post(
        "/api/v1/auth/login", json={"username": "analyst2", "password": "x"}
    )
    token = r.json()["access_token"]
    r = hist_client.post("/api/v1/history/run", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
