"""Background worker: thread pool for long jobs + optional automation scheduler.

Production upgrade path: swap the pool for Celery/Redis without changing
the job functions (documented in docs/ARCHITECTURE.md, decision A6).
"""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.db import session
from app.models import BackgroundJob, MarketCandle, TrainingRun
from app.timeutil import utcnow

logger = logging.getLogger("gmrai.worker")


def _job_session():
    return session()


def _update_job(db, job_id: int, **fields):
    job = db.get(BackgroundJob, job_id)
    if job is None:
        return
    for k, v in fields.items():
        setattr(job, k, v)
    db.commit()


def run_job(job_id: int, fn):
    """Execute fn(db) inside a job transaction wrapper."""
    db = _job_session()
    try:
        _update_job(db, job_id, status="running", started_at=utcnow())
        result = fn(db)
        _update_job(db, job_id, status="done", result_json=result, finished_at=utcnow())
        return result
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        _update_job(
            db,
            job_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            finished_at=utcnow(),
        )
        return None
    finally:
        db.close()


class Worker:
    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self.executor: ThreadPoolExecutor | None = None
        self._stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self.executor is None or getattr(self.executor, "_shutdown", False):
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="gmrai")
        return self.executor

    def submit(self, job_type: str, params: dict, fn) -> int:
        """Create a BackgroundJob row and schedule fn."""
        db = _job_session()
        job = BackgroundJob(job_type=job_type, params_json=params, status="pending")
        db.add(job)
        db.commit()
        job_id = job.id
        db.close()
        self._ensure_executor().submit(run_job, job_id, fn)
        return job_id

    def submit_training(self, config: dict) -> int:
        from app.services.training import TrainingConfig, run_training

        cfg = TrainingConfig(**{k: v for k, v in config.items() if k in TrainingConfig.__dataclass_fields__})
        db0 = _job_session()
        run_row = TrainingRun(
            model_type="hmm+random_forest",
            params_json=cfg.to_dict(),
            feature_version="v1",
            status="pending",
        )
        db0.add(run_row)
        db0.commit()
        run_id = run_row.id
        db0.close()
        return self.submit("training", cfg.to_dict(), lambda db: run_training(db, cfg, run_id=run_id))

    def submit_backtest(self, config: dict) -> int:
        from app.ml.backtest_engine import BacktestConfig, run_walk_forward
        from app.services.training import load_candles

        cfg = BacktestConfig(**{k: v for k, v in config.items() if k in BacktestConfig.__dataclass_fields__})
        from app.models import BacktestRun

        def _run(db):
            run_row = BacktestRun(name=config.get("name", f"wf-{utcnow().strftime('%H%M%S')}"), config_json=cfg.to_dict(), status="running")
            db.add(run_row)
            db.commit()
            rid = run_row.id
            df_m5, df_m15, df_h1 = load_candles(db)
            report = run_walk_forward(df_m5, df_m15, df_h1, cfg)
            run_row = db.get(BacktestRun, rid)
            run_row.status = "done"
            run_row.metrics_json = {
                "n_folds": report["n_folds"],
                "chosen_variant": report["chosen_variant"],
                "variant_comparison": report["variant_comparison"],
            }
            run_row.finished_at = utcnow()
            db.commit()
            return {"backtest_run_id": rid, "summary": run_row.metrics_json}

        return self.submit("backtest", cfg.to_dict(), _run)

    def submit_quality_check(self, symbol: str = "XAUUSD") -> int:
        from app.services.quality import run_quality_check

        def _run(db):
            out = {}
            for tf in ("M5", "M15", "H1"):
                out[tf] = run_quality_check(db, symbol, tf)
            return out

        return self.submit("quality_check", {"symbol": symbol}, _run)

    # ---- automation scheduler ----
    def start_scheduler(self) -> None:
        if not settings.automation_enabled:
            logger.info("Automation disabled — scheduler not started")
            return
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="gmrai-scheduler")
        self._scheduler_thread.start()
        logger.info("Automation scheduler started")

    def _scheduler_loop(self) -> None:
        import time

        last_quality = 0.0
        last_retrain = 0.0
        while not self._stop.wait(30):
            now = time.time()
            if now - last_quality >= settings.sync_check_interval_seconds:
                last_quality = now
                self.submit_quality_check()
            if now - last_retrain >= settings.retrain_check_interval_seconds:
                last_retrain = now
                self._maybe_retrain()

    def _maybe_retrain(self) -> None:
        db = _job_session()
        try:
            last_run = db.query(TrainingRun).order_by(TrainingRun.id.desc()).first()
            if last_run is None or last_run.finished_at is None:
                db.close()
                return
            candles_since = (
                db.query(MarketCandle)
                .filter(
                    MarketCandle.timeframe == "M15",
                    MarketCandle.ts > last_run.finished_at,
                )
                .count()
            )
        finally:
            db.close()
        # Trigger retrain if there is meaningful new data since last run.
        if candles_since >= settings.min_new_candles_for_retrain:
            logger.info("Triggering scheduled retrain (%d new candles)", candles_since)
            self.submit_training({})

    def stop(self) -> None:
        self._stop.set()
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)


worker = Worker()
