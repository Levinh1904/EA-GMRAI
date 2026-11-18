"""Change-password endpoint.

Security properties locked by these tests:
  * the CURRENT password is required (a stolen token is not enough)
  * the new password must pass strength checks
  * a successful change actually changes what login accepts
  * the response reissues a working access token
  * failures are logged
"""
import pytest

from app.models import SystemLog, User
from app.security.auth import hash_password

GOOD = "NewStrong-Pass99"   # >=10 chars, letters + digits


def _login(client, username: str, password: str):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_change_password_success_and_login_with_new(client, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "admin-pass",
            "new_password": GOOD,
            "confirm_password": GOOD,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["username"] == "admin"
    assert body["access_token"]

    # New password works, old one is rejected.
    assert _login(client, "admin", GOOD).status_code == 200
    assert _login(client, "admin", "admin-pass").status_code == 401

    # Reissued token is usable immediately.
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200


def test_change_password_requires_current_password(client, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": GOOD, "confirm_password": GOOD},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "hiện tại" in r.json()["detail"]
    # Password unchanged.
    assert _login(client, "admin", "admin-pass").status_code == 200


def test_change_password_rejects_mismatched_confirmation(client, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "admin-pass",
            "new_password": GOOD,
            "confirm_password": GOOD + "x",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "khớp" in r.json()["detail"]


def test_change_password_rejects_same_password(client, admin_token):
    r = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "admin-pass",
            "new_password": "admin-pass",
            "confirm_password": "admin-pass",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "weak",
    [
        "short1",                # too short (<10)
        "aaaaaaaaaaaa",          # letters only
        "1234567890123",         # digits only
        "password123",           # common/banned
        "aaaaaaaaaa1",           # too few distinct chars
    ],
)
def test_change_password_rejects_weak(client, admin_token, weak):
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "admin-pass", "new_password": weak, "confirm_password": weak},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code in (400, 422), r.text


def test_change_password_requires_auth(client):
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": GOOD, "confirm_password": GOOD},
    )
    assert r.status_code in (401, 403)


def test_change_password_logs_event(client, admin_token, db):
    from app.db import session

    client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "admin-pass", "new_password": GOOD, "confirm_password": GOOD},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    with session() as s:
        logged = (
            s.query(SystemLog)
            .filter(SystemLog.component == "auth")
            .all()
        )
    assert any("password changed" in r.message for r in logged)


def test_failed_change_is_logged(client, admin_token, db):
    from app.db import session

    client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "nope", "new_password": GOOD, "confirm_password": GOOD},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    with session() as s:
        logged = s.query(SystemLog).filter(SystemLog.component == "auth").all()
    assert any("failed password change" in r.message for r in logged)


def test_analyst_can_change_own_password(client, analyst_token):
    r = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "analyst-pass",
            "new_password": "AnotherGood-Pass7",
            "confirm_password": "AnotherGood-Pass7",
        },
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert r.status_code == 200, r.text
    assert _login(client, "analyst", "AnotherGood-Pass7").status_code == 200
