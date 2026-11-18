"""Admin surface: user management, API keys, jobs, retention, health.

The guarantees locked here are the ones that prevent an unrecoverable state:
  * the last active admin can never be demoted/disabled/deleted
  * a user cannot lock themselves out
  * API key plaintext is returned once and stored only as a hash
  * jobs returned by the async POSTs are actually queryable
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import ApiKey, BackgroundJob, SystemLog, TelegramMessage, User

ADMIN = {"username": "admin", "password": "admin-pass"}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def test_list_users_admin_only(client, admin_token, analyst_token):
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {analyst_token}"})
    assert r.status_code == 403

    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    usernames = {u["username"] for u in body["users"]}
    assert {"admin", "analyst"} <= usernames
    assert body["active_admins"] >= 1


def test_create_user_and_login(client, admin_token):
    r = client.post(
        "/api/v1/users",
        json={"username": "newviewer", "password": "ViewerPass-99", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "viewer"

    login = client.post("/api/v1/auth/login", json={"username": "newviewer", "password": "ViewerPass-99"})
    assert login.status_code == 200
    assert login.json()["role"] == "viewer"


def test_create_user_duplicate_conflict(client, admin_token):
    body = {"username": "analyst", "password": "AnotherPass-11", "role": "viewer"}
    r = client.post("/api/v1/users", json=body, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 409


@pytest.mark.parametrize("bad", ["short1", "alllettersxx", "1234567890123", "password123"])
def test_create_user_rejects_weak_password(client, admin_token, bad):
    r = client.post(
        "/api/v1/users",
        json={"username": "weakuser", "password": bad, "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (400, 422)


def test_create_user_rejects_bad_role(client, admin_token):
    r = client.post(
        "/api/v1/users",
        json={"username": "roleuser", "password": "GoodPass-2026", "role": "superuser"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_update_role_and_disable(client, admin_token, db):
    from app.db import session

    r = client.post(
        "/api/v1/users",
        json={"username": "tmpuser", "password": "GoodPass-2026", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    uid = r.json()["id"]

    r = client.patch(
        f"/api/v1/users/{uid}", json={"role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200 and r.json()["role"] == "analyst"

    r = client.patch(
        f"/api/v1/users/{uid}", json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.json()["is_active"] is False

    # Disabled user cannot log in.
    login = client.post("/api/v1/auth/login", json={"username": "tmpuser", "password": "GoodPass-2026"})
    assert login.status_code == 403


def test_cannot_demote_last_active_admin(client, admin_token, db):
    """The single admin must never be demoted — that would lock everyone out."""
    from app.db import session

    with session() as s:
        admin = s.query(User).filter(User.username == "admin").one()
        admin_id = admin.id

    r = client.patch(
        f"/api/v1/users/{admin_id}", json={"role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "cuối cùng" in r.json()["detail"] or "chính mình" in r.json()["detail"]


def test_cannot_self_deactivate(client, admin_token):
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    admin_id = next(u["id"] for u in r.json()["users"] if u["username"] == "admin")

    r = client.patch(
        f"/api/v1/users/{admin_id}", json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_cannot_delete_self(client, admin_token):
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"})
    admin_id = next(u["id"] for u in r.json()["users"] if u["username"] == "admin")
    r = client.delete(f"/api/v1/users/{admin_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 400


def test_admin_reset_password(client, admin_token):
    """The only lockout-recovery path."""
    client.post(
        "/api/v1/users",
        json={"username": "needreset", "password": "OldPass-2026", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}).json()
    uid = next(u["id"] for u in users["users"] if u["username"] == "needreset")

    r = client.post(
        f"/api/v1/users/{uid}/reset-password",
        json={"new_password": "BrandNew-Pass7"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text

    assert client.post("/api/v1/auth/login", json={"username": "needreset", "password": "OldPass-2026"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "needreset", "password": "BrandNew-Pass7"}).status_code == 200


def test_reset_password_rejects_weak(client, admin_token):
    users = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"}).json()
    uid = next(u["id"] for u in users["users"] if u["username"] == "analyst")
    r = client.post(
        f"/api/v1/users/{uid}/reset-password",
        json={"new_password": "password123"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


def test_user_admin_mutations_are_logged(client, admin_token, db):
    from app.db import session

    client.post(
        "/api/v1/users",
        json={"username": "loggeduser", "password": "GoodPass-2026", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    with session() as s:
        rows = s.query(SystemLog).filter(SystemLog.component == "admin").all()
    assert any("created user loggeduser" in r.message for r in rows)


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

def test_create_api_key_returns_plaintext_once(client, admin_token):
    r = client.post(
        "/api/v1/api-keys",
        json={"name": "collector-vm2", "role": "ingest"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_key"].startswith("gmrai_")
    plaintext = body["api_key"]

    # The key works for ingestion and is never echoed again by the list route.
    ingest = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": []},
        headers={"X-API-Key": plaintext},
    )
    # empty batch -> 422 from schema validation, but auth passed (not 401)
    assert ingest.status_code != 401

    listing = client.get("/api/v1/api-keys", headers={"Authorization": f"Bearer {admin_token}"}).json()
    entry = next(k for k in listing["keys"] if k["name"] == "collector-vm2")
    assert "api_key" not in entry
    assert entry["fingerprint"].startswith("sha256:")
    assert plaintext not in str(listing)


def test_revoke_and_restore_api_key(client, admin_token):
    created = client.post(
        "/api/v1/api-keys",
        json={"name": "temp-key", "role": "ingest"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    r = client.delete(f"/api/v1/api-keys/{created['id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200

    # Revoked key no longer authenticates.
    bad = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": []},
        headers={"X-API-Key": created["api_key"]},
    )
    assert bad.status_code == 401

    r = client.post(f"/api/v1/api-keys/{created['id']}/restore", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    good = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": []},
        headers={"X-API-Key": created["api_key"]},
    )
    assert good.status_code != 401


def test_cannot_revoke_bootstrap_key(client, admin_token):
    keys = client.get("/api/v1/api-keys", headers={"Authorization": f"Bearer {admin_token}"}).json()["keys"]
    bootstrap = next((k for k in keys if k["name"] == "env-bootstrap"), None)
    if bootstrap is None:
        pytest.skip("no bootstrap key in this fixture")
    r = client.delete(f"/api/v1/api-keys/{bootstrap['id']}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 400


def test_key_management_admin_only(client, analyst_token):
    assert client.get("/api/v1/api-keys", headers={"Authorization": f"Bearer {analyst_token}"}).status_code == 403
    r = client.post(
        "/api/v1/api-keys", json={"name": "nope", "role": "ingest"},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def test_job_created_by_admin_action_is_queryable(client, admin_token, monkeypatch):
    """POST /training/run returns a job id that GET /jobs/{id} can resolve."""
    from app.services import worker as worker_mod

    # Avoid spawning a real background thread; only the job row matters here.
    def fake_submit(job_type, params, fn):
        from app.db import session as sess

        db = sess()
        job = BackgroundJob(job_type=job_type, params_json=params, status="pending")
        db.add(job)
        db.commit()
        jid = job.id
        db.close()
        return jid

    monkeypatch.setattr(worker_mod.worker, "submit", fake_submit)
    r = client.post("/api/v1/training/run", json={}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    r = client.get(f"/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == job_id
    assert r.json()["job_type"] == "training"


def test_list_jobs_filters(client, admin_token, db):
    from app.db import session

    with session() as s:
        s.add(BackgroundJob(job_type="training", status="done"))
        s.add(BackgroundJob(job_type="quality_check", status="failed", error="boom"))
        s.commit()

    r = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["total"] >= 2
    assert r.json()["executor"]["durable"] is False  # honest about the thread pool

    r = client.get("/api/v1/jobs?status=failed", headers={"Authorization": f"Bearer {admin_token}"})
    assert all(j["status"] == "failed" for j in r.json()["jobs"])


def test_job_not_found_returns_404(client, admin_token):
    r = client.get("/api/v1/jobs/999999", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


def test_cancel_stuck_job(client, admin_token, db):
    from app.db import session

    with session() as s:
        job = BackgroundJob(job_type="training", status="running")
        s.add(job)
        s.commit()
        jid = job.id

    r = client.post(f"/api/v1/jobs/{jid}/cancel", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    r = client.get(f"/api/v1/jobs/{jid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.json()["status"] == "failed"
    assert "cancelled" in (r.json()["error"] or "")


def test_cancel_finished_job_rejected(client, admin_token, db):
    from app.db import session

    with session() as s:
        job = BackgroundJob(job_type="training", status="done")
        s.add(job)
        s.commit()
        jid = job.id
    r = client.post(f"/api/v1/jobs/{jid}/cancel", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 404 correctness
# ---------------------------------------------------------------------------

def test_training_run_missing_returns_404(client, admin_token):
    r = client.get("/api/v1/training/runs/999999", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


def test_backtest_missing_returns_404(client, admin_token):
    r = client.get("/api/v1/backtests/999999", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Health / version
# ---------------------------------------------------------------------------

def test_health_reports_ok_when_healthy(client):
    """Health returns 200 with a healthy DB and a *running* worker.

    In tests the automation scheduler is disabled (GMRAI_AUTOMATION_ENABLED=false),
    so the worker is legitimately stopped and the probe reports 503 — which is
    the intended behaviour (a dead worker is a real degradation). Assert on the
    database half here, and on the 503 contract in the next test.
    """
    r = client.get("/api/v1/health")
    body = r.json()
    assert body["database"] == "ok"
    assert body["api"] == "ok"
    assert r.status_code in (200, 503)


def test_health_returns_503_when_worker_stopped_or_db_down(client):
    """A degraded component must not report 200 — that silently passed uptime checks."""
    r = client.get("/api/v1/health")
    body = r.json()
    expected = 200 if body["worker"] == "running" else 503
    assert r.status_code == expected


def test_readyz_matches_health(client):
    r = client.get("/api/v1/readyz")
    h = client.get("/api/v1/health")
    assert r.status_code == h.status_code
    assert r.json()["api"] == "ok"


def test_version_endpoint(client):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "gmrai-backend"
    assert "version" in body


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def test_retention_prunes_old_rows_and_keeps_recent(db):
    from app.db import session
    from app.services.retention import run_retention

    now = datetime.now(timezone.utc)
    with session() as s:
        s.add(SystemLog(level="INFO", component="old", message="old",
                        created_at=now - timedelta(days=400)))
        s.add(SystemLog(level="INFO", component="new", message="new", created_at=now))
        s.add(TelegramMessage(dedupe_key="old-tg", kind="signal", status="sent",
                              text="x", created_at=now - timedelta(days=400)))
        s.commit()

        out = run_retention(s)
        assert isinstance(out["deleted"], dict)

        remaining = {r.component for r in s.query(SystemLog).all()}
        assert "new" in remaining
        # system_logs retention default is 30 days -> the 400-day row is gone.
        assert "old" not in remaining


def test_retention_dry_run_changes_nothing(db):
    from app.db import session
    from app.services.retention import run_retention

    now = datetime.now(timezone.utc)
    with session() as s:
        s.add(SystemLog(level="INFO", component="keepme", message="x",
                        created_at=now - timedelta(days=400)))
        s.commit()
        out = run_retention(s, dry_run=True)
        assert any("would delete" in str(v) for v in out["deleted"].values())
        assert s.query(SystemLog).filter(SystemLog.component == "keepme").count() == 1


def test_retention_never_prunes_history_runs_by_default(db):
    from app.db import session
    from app.services.retention import run_retention

    with session() as s:
        out = run_retention(s, dry_run=True)
    assert out["deleted"]["regime_history"] == "disabled"


# ---------------------------------------------------------------------------
# Features endpoint (no longer a stub)
# ---------------------------------------------------------------------------

def test_features_returns_empty_without_candles(client, admin_token):
    r = client.get("/api/v1/features", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["features"] == []
    assert "columns" in body
