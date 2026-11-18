"""API tests: auth, ingestion, market, regime degradation, permissions."""
from datetime import datetime, timedelta, timezone

from app.config import settings


def _candles(n=5, tf="M15", start=None):
    now = start or datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    step = {"M5": 5, "M15": 15, "H1": 60}[tf]
    return [
        {
            "symbol": "XAUUSD",
            "ts": (now - timedelta(minutes=step * i)).isoformat(),
            "open": 2400.0 + i,
            "high": 2401.0 + i,
            "low": 2399.0 + i,
            "close": 2400.5 + i,
            "tick_volume": 100 + i,
            "spread": 25,
        }
        for i in range(n)
    ]


def test_health_public(client):
    assert client.get("/health").status_code == 200
    r = client.get("/api/v1/health").json()
    assert r["api"] == "ok" and r["database"] == "ok"


def test_login_and_me(client, admin_token):
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


def test_market_requires_auth(client):
    assert client.get("/api/v1/market/latest").status_code in (401, 403)


def test_ingest_requires_api_key(client):
    r = client.post("/api/v1/ingest/candles?timeframe=M15", json={"candles": _candles()})
    assert r.status_code == 401


def test_ingest_with_env_key(client):
    r = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": _candles()},
        headers={"X-API-Key": settings.api_key},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 5


def test_ingest_duplicate_upsert(client):
    headers = {"X-API-Key": settings.api_key}
    body = {"candles": _candles()}
    client.post("/api/v1/ingest/candles?timeframe=M15", json=body, headers=headers)
    r = client.post("/api/v1/ingest/candles?timeframe=M15", json=body, headers=headers)
    assert r.json()["updated"] == 5 and r.json()["inserted"] == 0


def test_ingest_rejects_forming(client):
    # candle "now" is still forming -> rejected
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candles = [_candles(1, "M15")[0]]
    candles[0]["ts"] = now.isoformat()
    r = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": candles},
        headers={"X-API-Key": settings.api_key},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] == 1


def test_market_candles_pagination(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}", "X-API-Key": settings.api_key}
    client.post("/api/v1/ingest/candles?timeframe=M15", json={"candles": _candles(20)}, headers=headers)
    r = client.get("/api/v1/market/candles?timeframe=M15&limit=7", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 20 and len(body["candles"]) == 7


def test_regime_returns_trade_ens_only(client, admin_token):
    r = client.get("/api/v1/regime/latest", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["regime"] == "TRADE_ENS"
    assert body["permission"] == "NO_TRADE"
    assert body["trade_ens"] is None  # no model in isolated test DB
    assert "NO_APPROVED_MODEL" in body["reason_codes"]
    assert "TREND_UP" not in r.text and "SIDEWAYS" not in r.text


def test_stats_dashboard(client, admin_token):
    r = client.get("/api/v1/stats/dashboard", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert "candles" in body and "trade_ens" in body
    assert set(body.get("active_models", {}).keys()) == {"trade_ens"}


def test_analyst_cannot_start_training(client, analyst_token):
    r = client.post("/api/v1/training/run", json={}, headers={"Authorization": f"Bearer {analyst_token}"})
    assert r.status_code == 403


def test_admin_can_start_training(client, admin_token, monkeypatch):
    # Patch the real worker so no background thread races with test teardown.
    from app.services import worker as worker_mod

    calls = []
    monkeypatch.setattr(worker_mod.worker, "submit_training", lambda cfg: calls.append(cfg) or 42)
    r = client.post("/api/v1/training/run", json={}, headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["job_id"] == 42
    assert len(calls) == 1


def test_backtest_list(client, admin_token):
    r = client.get("/api/v1/backtests", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200


def test_models_list_empty(client, admin_token):
    r = client.get("/api/v1/models", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["models"] == []


def test_system_status(client, admin_token):
    r = client.get("/api/v1/system/status", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200


def test_market_candles_single_source(client, admin_token):
    """Khi có nhiều nguồn (ftmo + synthetic), /market/candles chỉ trả 1 nguồn."""
    headers = {"Authorization": f"Bearer {admin_token}", "X-API-Key": settings.api_key}
    # ftmo nến tại :00
    client.post("/api/v1/ingest/candles?timeframe=M15", json={"candles": _candles(3, "M15", start=datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc))}, headers=headers)
    # synthetic nến lệch +4 phút (mô phỏng demo data đan xen)
    synth = _candles(3, "M15", start=datetime(2026, 2, 3, 12, 4, tzinfo=timezone.utc))
    for c in synth:
        c["source"] = "synthetic_demo"
    client.post("/api/v1/ingest/candles?timeframe=M15", json={"candles": synth}, headers=headers)
    r = client.get("/api/v1/market/candles?timeframe=M15&limit=100", headers={"Authorization": f"Bearer {admin_token}"})
    body = r.json()
    sources = {c["source"] for c in body["candles"]}
    assert len(sources) == 1, f"mixed sources: {sources}"
    assert body["source"] == "ftmo_mt5"


def test_tick_feed(client, admin_token):
    """POST tick (API key) -> GET tick trả giá live + age."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/market/tick", headers=headers)
    assert r.status_code == 200 and r.json()["live"] is False  # chưa có tick

    r = client.post("/api/v1/market/tick", json={"symbol": "XAUUSD", "bid": 4004.5, "ask": 4004.8, "spread": 3},
                    headers={"X-API-Key": settings.api_key})
    assert r.status_code == 200

    r = client.get("/api/v1/market/tick", headers=headers)
    body = r.json()
    assert body["live"] is True
    assert body["bid"] == 4004.5 and body["ask"] == 4004.8
    assert body["age_seconds"] is not None and body["stale"] is False
    assert body["note"]  # nhãn "chỉ hiển thị"

    # tick yêu cầu API key khi POST
    r = client.post("/api/v1/market/tick", json={"symbol": "XAUUSD", "bid": 1, "ask": 1})
    assert r.status_code == 401
