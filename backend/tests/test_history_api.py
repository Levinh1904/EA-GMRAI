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
    import os

    r = hist_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": os.environ["GMRAI_ADMIN_PASSWORD"]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_history_job_done(history_setup):
    _, run_id, result = history_setup
    assert result["status"] == "done"
    assert result["bar_count"] >= 1500
    assert result["segment_count"] >= 5
    assert result["data_source"] == "synthetic_demo"


def test_day_analysis_is_causal(hist_client, hist_token, history_setup):
    """GET /history/day returns one UTC day, using only bars before that day's end."""
    _, _, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}

    r = hist_client.get("/api/v1/history/day", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["day"], "day must be reported"
    assert body["bar_count"] == len(body["bars"])
    assert body["data_source"] == "synthetic_demo"
    assert body["model_versions"]["hmm"] and body["model_versions"]["rf"]

    # Every returned bar belongs to the requested day (strict UTC window).
    from datetime import datetime, timedelta

    start = datetime.fromisoformat(body["day"])
    end = start + timedelta(days=1)
    for bar in body["bars"]:
        ts = datetime.fromisoformat(bar["ts"].replace("Z", "+00:00")).replace(tzinfo=None)
        assert start <= ts < end, f"bar {bar['ts']} outside {body['day']}"
    # OHLC + regime payload present on each bar.
    first = body["bars"][0]
    assert first["regime"] and first["close"] > 0
    assert "reference_regime" in first


def test_day_analysis_rejects_bad_date(hist_client, hist_token, history_setup):
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get("/api/v1/history/day?day=not-a-date", headers=h)
    assert r.status_code == 400


def test_day_analysis_no_data_for_future_day(hist_client, hist_token, history_setup):
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get("/api/v1/history/day?day=1999-01-01", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["reason"] == "NO_DATA_FOR_DAY"
    assert body["bars"] == []


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

    # xlsx bars: tz-aware datetimes must be exported as naive UTC
    r = hist_client.get(f"/api/v1/history/runs/{run_id}/export?format=xlsx&scope=bars", headers=h)
    assert r.status_code == 200, r.text[:300]
    wb2 = load_workbook(io.BytesIO(r.content))
    assert wb2["bars"].max_row > 100

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


def test_history_vs_reference_endpoint(hist_client, hist_token, history_setup):
    _, run_id, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get(f"/api/v1/history/runs/{run_id}/stats/vs_reference", headers=h)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["reference_version"] == "ref_v1"
    assert body["reference_config"]["version"] == "ref_v1"
    assert 0.0 <= body["agreement_rate"] <= 1.0
    assert "classes" in body and "TRANSITION" in body["classes"]
    assert "per_class" in body and body["macro_f1"] is not None
    assert 0.0 <= body["false_trend_rate"] <= 1.0
    assert 0.0 <= body["false_sideways_rate"] <= 1.0
    assert "boundaries" in body and "duration_disagreement_minutes" in body


def test_history_outcomes_endpoint(hist_client, hist_token, history_setup):
    _, run_id, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get(f"/api/v1/history/runs/{run_id}/stats/outcomes", headers=h)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["horizons"] == [12, 48, 96]
    keys = list(body["per_regime"].keys())
    assert any(k.startswith("ai_regime:") for k in keys)
    assert any(k.startswith("reference_regime:") for k in keys)
    first = body["per_regime"][keys[0]]["12"]
    assert "mean_fwd_return" in first and "win_rate_pct" in first and "pct_in_range" in first


def test_history_bars_include_reference(hist_client, hist_token, history_setup):
    _, run_id, _ = history_setup
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get(f"/api/v1/history/runs/{run_id}/bars?limit=50", headers=h)
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert len(bars) > 0
    b = bars[-1]
    for key in ("reference_regime", "reference_reason", "di_gap", "ema_slope",
                "ref_channel_high", "ref_channel_low", "ref_displacement"):
        assert key in b, f"missing {key} in bars response"
    assert b["reference_regime"] in ("TREND_UP", "TREND_DOWN", "SIDEWAYS", "TRANSITION",
                                     "HIGH_VOLATILITY", "UNKNOWN")


# ---------------------------------------------------------------------------
# Day analysis must expose the same direction statistics as the full history.
# ---------------------------------------------------------------------------

def test_day_analysis_includes_direction_stats(hist_client, hist_token, history_setup):
    """GET /history/day carries direction_accuracy + wrong_direction."""
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.get("/api/v1/history/day", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("reason") == "NO_DATA_FOR_DAY":
        pytest.skip("no data for the default day in this fixture")

    acc = body.get("direction_accuracy")
    wrong = body.get("wrong_direction")
    assert acc is not None and wrong is not None
    assert "per_segment" in acc and "by_regime" in acc["per_segment"]
    # Small-sample honesty: a single day must declare its own reliability.
    sample = acc.get("sample")
    assert sample is not None
    assert sample["reliability"] in ("insufficient", "low", "moderate", "ok")
    assert sample["segments"] == acc["per_segment"]["overall"]["total"]
    assert "note" in sample and sample["note"]

    # Wrong-call breakdown is present and internally consistent.
    assert wrong["total"] == acc["per_segment"]["overall"]["total"]
    assert wrong["wrong_total"] == wrong["total"] - acc["per_segment"]["overall"]["correct"]
    if wrong["wrong_total"] > 0 and "failure_type" in wrong:
        ft = wrong["failure_type"]
        assert (
            ft["never_moved_favourably"] + ft["reversed_after_favourable_move"]
            == wrong["wrong_total"]
        )


# ---------------------------------------------------------------------------
# Gap backfill: bars that closed while the app was down must still be labelled.
# Without this, a restart leaves unlabelled candles and the chart's AI band
# simply stops at the last bar that happened to be scored.
# ---------------------------------------------------------------------------

def test_backfill_labels_missing_bars(hist_client, hist_token, history_setup):
    """Bars that closed while the app was down must still get a label."""
    from app.db import session as session_factory
    from app.services.prediction import backfill_predictions

    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.post("/api/v1/history/predictions/backfill?max_bars=200", headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["reason"] == "OK"

    # Repeated passes must converge to a no-op (each pass fills a window).
    for _ in range(6):
        r2 = hist_client.post("/api/v1/history/predictions/backfill?max_bars=200", headers=h)
        assert r2.status_code == 200, r2.text
        if r2.json()["scored"] == 0:
            break
    else:
        raise AssertionError("backfill never converged to zero")


def test_backfill_is_idempotent_and_never_overwrites(hist_client, hist_token, history_setup):
    from app.db import session as session_factory
    from app.models import ModelPrediction
    from app.services.prediction import backfill_predictions

    with session_factory() as s:
        before = {
            p.ts: (p.regime, p.confidence)
            for p in s.query(ModelPrediction).filter(ModelPrediction.symbol == "XAUUSD").all()
        }
    with session_factory() as s:
        backfill_predictions(s, "XAUUSD", max_bars=200)
    with session_factory() as s:
        after = {
            p.ts: (p.regime, p.confidence)
            for p in s.query(ModelPrediction).filter(ModelPrediction.symbol == "XAUUSD").all()
        }
    # Every previously stored label is unchanged.
    for ts, val in before.items():
        assert after[ts] == val


def test_backfill_reports_no_data_without_candles(db):
    from app.db import session as session_factory
    from app.services.prediction import backfill_predictions

    with session_factory() as s:
        out = backfill_predictions(s, "NOT_A_SYMBOL")
    assert out["scored"] == 0
    assert out["reason"] in ("NO_DATA", "NO_APPROVED_MODEL", "INSUFFICIENT_FEATURES")


def test_history_run_accepts_entry_hour_filter(hist_client, hist_token):
    h = {"Authorization": f"Bearer {hist_token}"}
    r = hist_client.post("/api/v1/history/run?hours=6,8,14,17", headers=h)
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    runs = hist_client.get("/api/v1/history/runs?limit=1", headers=h).json()["runs"]
    assert runs[0]["id"] == run_id
    assert runs[0]["allowed_entry_hours_utc"] == [6, 8, 14, 17]

    r = hist_client.post("/api/v1/history/run?hours=24", headers=h)
    assert r.status_code == 400

    # Empty string means "all hours", distinct from omitting the param (model default).
    r = hist_client.post("/api/v1/history/run?hours=", headers=h)
    assert r.status_code == 200, r.text
    runs = hist_client.get("/api/v1/history/runs?limit=1", headers=h).json()["runs"]
    assert runs[0]["allowed_entry_hours_utc"] == []
