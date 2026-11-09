"""Seed the database with clearly-labeled synthetic XAUUSD candles (DEMO).

Usage (from backend/):
    .venv/bin/python ../scripts/seed_demo_data.py [--bars 9000] [--train]

Data source is ALWAYS 'synthetic_demo'; the dashboard shows a DEMO banner
for this source. This script exists so the platform can be exercised
end-to-end without MT5 — never presented as live data.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import Base, get_engine, session
from app.ml.synthetic import generate_synthetic_candles
from app.services.ingestion import ingest_candles
from app.services.quality import run_quality_check
from app.timeutil import utcnow


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=9000, help="number of M15 bars")
    ap.add_argument("--train", action="store_true", help="run training after seeding")
    args = ap.parse_args()

    get_engine()
    Base.metadata.create_all(get_engine())

    df_m5, df_m15, df_h1, _ = generate_synthetic_candles(n_m15=args.bars, seed=42)
    now = utcnow().replace(second=0, microsecond=0)
    end = df_m15.index.max()
    shift = now - (end + timedelta(minutes=15))

    with session() as db:
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
            total = {"received": 0, "inserted": 0, "updated": 0, "rejected": 0}
            for i in range(0, len(candles), 10_000):
                out = ingest_candles(db, candles[i : i + 10_000], tf, collector_id="seed-script", now=now)
                for k in total:
                    total[k] += out[k]
            print(f"[seed] {tf}: {total}")
        for tf in ("M5", "M15", "H1"):
            q = run_quality_check(db, "XAUUSD", tf, now=now)
            print(f"[quality] {tf}: gaps={q['gap_count']} stale={q['stale']}")

    if args.train:
        from app.services.training import TrainingConfig, run_training

        with session() as db:
            summary = run_training(db, TrainingConfig())
        print("[train] summary:", {k: summary[k] for k in ("hmm_model_id", "rf_model_id", "chosen_variant", "auto_approved")})
        print("[train] chosen test macro F1:", summary["variant_results"][summary["chosen_variant"]]["test_macro_f1"])
        print("[train] ONNX parity:", summary["onnx_parity"])


if __name__ == "__main__":
    main()
