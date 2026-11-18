"""trade_ens API: honest no-model behaviour and admin-only training."""
from __future__ import annotations


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_status_without_approved_model(client, admin_token):
    r = client.get("/api/v1/trade-model/status", headers=_h(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["model_name"] == "trade_ens"
    assert body["approved"] is False
    assert body["code"] == "NO_APPROVED_MODEL"


def test_signal_without_model_returns_explicit_code(client, admin_token):
    r = client.get("/api/v1/trade-model/signal", headers=_h(admin_token))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_APPROVED_MODEL"


def test_deployability_without_model_is_not_ready(client, admin_token):
    r = client.get("/api/v1/trade-model/deployability", headers=_h(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["demo_ready"] is False
    assert body["live_ready"] is False
    assert "NO_APPROVED_MODEL" in body["blockers"]


def test_history_without_model_returns_explicit_code(client, admin_token):
    r = client.get("/api/v1/trade-model/history", headers=_h(admin_token))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_APPROVED_MODEL"


def test_reference_without_candles_is_empty_not_fabricated(client, admin_token):
    r = client.get("/api/v1/reference/latest", headers=_h(admin_token))
    assert r.status_code == 200
    assert r.json()["status"] == "no_data"


def test_only_admin_can_start_trade_training(client, analyst_token):
    r = client.post("/api/v1/trade-model/train", headers=_h(analyst_token))
    assert r.status_code == 403
