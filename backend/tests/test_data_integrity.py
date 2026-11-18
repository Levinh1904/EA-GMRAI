"""Regression tests for data-integrity fixes:

1. Live regime inference is idempotent per bar (no duplicate rows, no double
   hysteresis step on repeated polling).
2. Candle upsert is keyed by (ts, source) — feeds never overwrite each other.
3. Training/backtest purge the label horizon between subtrain and subval.
4. Security: placeholder secrets are refused and env API key needs a real value.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.ml.splits import purged_subtrain_subval
from app.models import MarketCandle, ModelPrediction
from app.services.ingestion import ingest_candles


def _candle(ts, source="ftmo_mt5", close=2400.0, **kw):
    """Service-level candle (datetime ts) — the API schema handles ISO strings."""
    return {
        "symbol": "XAUUSD",
        "ts": ts,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "tick_volume": 100,
        "source": source,
        **kw,
    }


def _api_candles(ts, source="ftmo_mt5", close=2400.0):
    return [dict(_candle(ts, source, close), ts=ts.isoformat())]


# --------------------------------------------------------------- purge

def test_purged_subtrain_subval_drops_label_horizon():
    sub = purged_subtrain_subval((0, 700), (700, 850), embargo=12)
    assert sub["subtrain"] == (0, 688)
    assert sub["subval"] == (700, 838)
    # No overlap, and each region is separated from the next by the horizon.
    assert sub["subtrain"][1] + 12 == sub["subval"][0]


def test_purged_subtrain_subval_rejects_empty_region():
    with pytest.raises(ValueError):
        purged_subtrain_subval((0, 5), (5, 20), embargo=12)


def test_training_uses_purged_split(db):
    """The training summary must record the purge, proving the horizon is applied."""
    from tests.test_training_pipeline import _seed_synthetic
    from app.db import session
    from app.services.training import TrainingConfig, run_training

    with session() as s:
        _seed_synthetic(s, n_m15=2600)
        summary = run_training(
            s,
            TrainingConfig(hmm_n_states=5, hmm_n_init=2, seed=42, train_frac=0.6, val_frac=0.2),
        )
    assert summary["purge_bars"] == 12
    rng = summary["dataset_range"]
    assert rng["subtrain"][1] + 12 == rng["subval"][0]
    assert rng["subval"][1] <= rng["test"][0]
    assert summary["data_source"] == "synthetic_demo"


# ------------------------------------------------------- source isolation

def test_upsert_keyed_by_source_does_not_overwrite_other_feed(db):
    from app.db import session

    now = datetime(2026, 3, 2, 12, 30, tzinfo=timezone.utc)
    ts = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    with session() as s:
        ingest_candles(s, [_candle(ts, "ftmo_mt5", 4000.0)], "M15", now=now)
        # Same timestamp, different feed (demo prices) -> separate row.
        ingest_candles(s, [_candle(ts, "synthetic_demo", 1900.0)], "M15", now=now)
        rows = s.query(MarketCandle).order_by(MarketCandle.source).all()
        assert len(rows) == 2
        assert {(r.source, r.close) for r in rows} == {
            ("ftmo_mt5", 4000.0),
            ("synthetic_demo", 1900.0),
        }

        # Re-sending the real feed updates only the real row.
        ingest_candles(s, [_candle(ts, "ftmo_mt5", 4001.0)], "M15", now=now)
        ftmo = s.query(MarketCandle).filter(MarketCandle.source == "ftmo_mt5").one()
        demo = s.query(MarketCandle).filter(MarketCandle.source == "synthetic_demo").one()
        assert ftmo.close == 4001.0
        assert demo.close == 1900.0


def test_quality_and_stats_use_single_source(db):
    from app.db import session
    from app.services.quality import run_quality_check
    from app.services.stats import dashboard_stats

    now = datetime(2026, 3, 2, 12, 30, tzinfo=timezone.utc)
    times = [now - timedelta(minutes=15 * (i + 1)) for i in range(10)]
    with session() as s:
        ingest_candles(s, [_candle(t, "ftmo_mt5", 4000.0) for t in times], "M15", now=now)
        # Demo feed at *offset* timestamps: mixing them would fake duplicates/gaps.
        ingest_candles(
            s,
            [_candle(t + timedelta(minutes=4), "synthetic_demo", 1900.0) for t in times],
            "M15",
            now=now,
        )
        out = run_quality_check(s, "XAUUSD", "M15", now=now)
        assert out["total_candles"] == 10
        assert out["duplicate_count"] == 0 and out["gap_count"] == 0

        stats = dashboard_stats(s, "XAUUSD")
        assert stats["data_source"] == "ftmo_mt5"
        assert stats["candles"]["M15"]["count"] == 10


# ----------------------------------------------------- idempotent regime

def test_regime_prediction_is_idempotent_per_bar(db, monkeypatch):
    """Repeated polls for the same M15 bar persist ONE row and do not double-step."""
    from app.db import session
    import app.services.prediction as pred_mod
    from tests.test_training_pipeline import _seed_synthetic
    from app.services.training import TrainingConfig, run_training
    from app.services.registry import set_version_status
    from app.models import ModelVersion

    with session() as s:
        _seed_synthetic(s, n_m15=2200)
        summary = run_training(
            s,
            TrainingConfig(hmm_n_states=5, hmm_n_init=2, seed=7, train_frac=0.6, val_frac=0.2),
        )
        for vid in (summary["hmm_version_id"], summary["rf_version_id"]):
            set_version_status(s, s.get(ModelVersion, vid), "approved", force=True)

    # Bypass the in-process TTL cache: the DB-level guarantee is what we test.
    monkeypatch.setattr(pred_mod, "_REGIME_CACHE_TTL", -1.0)

    with session() as s:
        first = pred_mod.compute_latest_regime(s, "XAUUSD")
        assert first["cached"] is False
        count_after_first = s.query(ModelPrediction).count()

        second = pred_mod.compute_latest_regime(s, "XAUUSD")
        third = pred_mod.compute_latest_regime(s, "XAUUSD")

        assert s.query(ModelPrediction).count() == count_after_first == 1
        assert second["cached"] is True and third["cached"] is True
        assert second["regime"] == first["regime"]
        assert second["timestamp"] == first["timestamp"]
        # Stored row count per bar stays exactly one.
        bar_ts = datetime.fromisoformat(first["timestamp"])
        ts_count = s.query(ModelPrediction).filter(ModelPrediction.ts == bar_ts).count()
        assert ts_count == 1


def test_regime_unique_constraint_blocks_duplicate_bar(db):
    from app.db import session
    from sqlalchemy.exc import IntegrityError

    ts = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    with session() as s:
        s.add(ModelPrediction(model_version_id=1, symbol="XAUUSD", timeframe="M15", ts=ts, regime="SIDEWAYS"))
        s.commit()
        s.add(ModelPrediction(model_version_id=1, symbol="XAUUSD", timeframe="M15", ts=ts, regime="TREND_UP"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()


# --------------------------------------------------------------- secrets

def test_placeholder_secrets_are_rejected():
    bad = Settings(
        _env_file=None,
        secret_key="dev-secret-change-me-in-production",
        api_key="dev-ingest-key-change-me",
        admin_password="admin-change-me",
    )
    assert set(bad.weak_secrets) == {
        "GMRAI_SECRET_KEY",
        "GMRAI_API_KEY",
        "GMRAI_ADMIN_PASSWORD",
    }
    with pytest.raises(RuntimeError):
        bad.assert_secure()


def test_strong_secrets_pass_and_weak_override_allowed():
    strong = Settings(
        _env_file=None,
        secret_key="a" * 64,
        api_key="gmrai_" + "b" * 32,
        admin_password="c" * 24,
    )
    assert strong.weak_secrets == []
    strong.assert_secure()

    weak_but_allowed = Settings(
        _env_file=None, secret_key="", api_key="", admin_password="", allow_weak_secrets=True
    )
    weak_but_allowed.assert_secure()


def test_ingest_rejects_placeholder_env_key(client):
    """An unset/placeholder GMRAI_API_KEY must never authenticate ingestion."""
    from app.config import settings

    r = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": _api_candles(datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc))},
        headers={"X-API-Key": "dev-ingest-key-change-me"},
    )
    assert r.status_code == 401
    # The real configured key still works.
    r = client.post(
        "/api/v1/ingest/candles?timeframe=M15",
        json={"candles": _api_candles(datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc))},
        headers={"X-API-Key": settings.api_key},
    )
    assert r.status_code == 200, r.text
