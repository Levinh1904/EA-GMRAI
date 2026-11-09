"""Full training pipeline E2E on clearly-labeled synthetic data."""
from datetime import datetime, timedelta, timezone

from app.ml.synthetic import generate_synthetic_candles
from app.models import HmmModel, ModelVersion, RandomForestModel
from app.services.ingestion import ingest_candles
from app.services.training import TrainingConfig, run_training


def _seed_synthetic(db, n_m15=2600):
    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=n_m15, seed=99)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = df_m15.index.max()
    shift = now - (end + timedelta(minutes=15))
    for df, tf in ((df_m5, "M5"), (df_m15, "M15"), (df_h1, "H1")):
        candles = [
            {
                "symbol": "XAUUSD",
                "ts": (idx + shift).to_pydatetime(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "tick_volume": int(r["tick_volume"]),
                "spread": int(r["spread"]),
                "source": "synthetic_demo",
            }
            for idx, r in df.iterrows()
        ]
        ingest_candles(db, candles, tf, collector_id="test-seed", now=now + timedelta(hours=1))
    return now


def test_training_pipeline_e2e(db):
    from app.db import session

    with session() as s:
        _seed_synthetic(s)
        cfg = TrainingConfig(hmm_n_states=5, hmm_n_init=3, seed=42, train_frac=0.6, val_frac=0.2)
        summary = run_training(s, cfg)

    assert summary["hmm_model_id"] and summary["rf_model_id"]
    assert set(summary["state_mapping"].keys()) == {str(i) for i in range(5)}
    assert summary["chosen_variant"] in {"hmm_only", "rf_only", "combined"}
    assert "engine_params" in summary and summary["engine_params"]["confirm_bars"] >= 1
    assert summary["onnx_parity"]["passed"], summary["onnx_parity"]
    assert summary["variant_results"][summary["chosen_variant"]]["test_macro_f1"] >= 0.0
    assert "auto_approved" in summary  # gate evaluated, never silently skipped

    # registry rows + artifacts on disk
    from pathlib import Path

    with session() as s:
        hmm = s.get(HmmModel, summary["hmm_model_id"])
        rf = s.get(RandomForestModel, summary["rf_model_id"])
        hv = s.get(ModelVersion, summary["hmm_version_id"])
        rv = s.get(ModelVersion, summary["rf_version_id"])
        assert hmm.artifact_path and Path(hmm.artifact_path).exists()
        assert rf.artifact_path and Path(rf.artifact_path).exists()
        assert rf.onnx_path and Path(rf.onnx_path).exists()
        assert hv.status in ("candidate", "approved")
        assert rv.status in ("candidate", "approved")
        assert len(hmm.state_mapping_json) == 5


def test_training_insufficient_data(db):
    from app.db import session

    with session() as s:
        import pytest

        with pytest.raises(ValueError):
            run_training(s, TrainingConfig(hmm_n_init=2))
