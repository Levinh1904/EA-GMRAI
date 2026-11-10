"""SQLAlchemy models — all tables. Schema doc: docs/DATABASE_SCHEMA.md."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.timeutil import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="ingest")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "ts", name="uq_candle_key"),
        Index("ix_candle_sym_tf_ts", "symbol", "timeframe", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    tick_volume: Mapped[int] = mapped_column(Integer, default=0)
    spread: Mapped[int | None] = mapped_column(Integer, nullable=True)
    real_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="ftmo_mt5")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DataSyncLog(Base):
    __tablename__ = "data_sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_id: Mapped[str] = mapped_column(String(64), default="unknown")
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    candles_received: Mapped[int] = mapped_column(Integer, default=0)
    candles_inserted: Mapped[int] = mapped_column(Integer, default=0)
    candles_updated: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / partial / error
    message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"
    __table_args__ = (Index("ix_quality_sym_tf_checked", "symbol", "timeframe", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_candles: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    gap_count: Mapped[int] = mapped_column(Integer, default=0)
    bad_candle_count: Mapped[int] = mapped_column(Integer, default=0)
    stale_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MarketFeature(Base):
    __tablename__ = "market_features"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "ts", "feature_version", name="uq_feature_key"),
        Index("ix_feature_sym_tf_ts", "symbol", "timeframe", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_version: Mapped[str] = mapped_column(String(16), default="v1")

    ret1: Mapped[float | None] = mapped_column(Float, nullable=True)
    ret4: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    adx_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    di_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1_ema_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1_atr_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1_adx_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1_trend_context: Mapped[float | None] = mapped_column(Float, nullable=True)
    m5_ret_short: Mapped[float | None] = mapped_column(Float, nullable=True)
    m5_vol_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    m5_momentum: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HmmModel(Base):
    __tablename__ = "hmm_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    n_states: Mapped[int] = mapped_column(Integer, default=5)
    covariance_type: Mapped[str] = mapped_column(String(16), default="diag")
    feature_version: Mapped[str] = mapped_column(String(16), default="v1")
    hyperparams_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dataset_range_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    state_mapping_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transition_matrix_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    train_log_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_log_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="training")
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RandomForestModel(Base):
    __tablename__ = "random_forest_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    feature_version: Mapped[str] = mapped_column(String(16), default="v1")
    label_spec_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hyperparams_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dataset_range_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feature_importances_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="training")
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    onnx_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_type: Mapped[str] = mapped_column(String(16))  # hmm / random_forest
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="training")  # training/validating/candidate/approved/rejected/archived
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    __table_args__ = (Index("ix_pred_sym_tf_ts", "symbol", "timeframe", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    regime: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    probabilities_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    components_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_codes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    permission: Mapped[str] = mapped_column(String(16), default="NO_TRADE")
    expiry_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_type: Mapped[str] = mapped_column(String(16))
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dataset_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(16), default="v1")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hmm_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rf_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(Integer, index=True)
    metric_name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemLog(Base):
    __tablename__ = "system_logs"
    __table_args__ = (Index("ix_syslog_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    component: Mapped[str] = mapped_column(String(64), default="system")
    message: Mapped[str] = mapped_column(String(1024))
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegimeHistoryRun(Base):
    __tablename__ = "regime_history_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), default="XAUUSD")
    timeframe: Mapped[str] = mapped_column(String(8), default="M15")
    hmm_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rf_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(16), default="v1")
    data_source: Mapped[str] = mapped_column(String(32), default="ftmo_mt5")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bar_count: Mapped[int] = mapped_column(Integer, default=0)
    segment_count: Mapped[int] = mapped_column(Integer, default=0)
    data_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reference_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reference_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegimeHistoryBar(Base):
    __tablename__ = "regime_history_bars"
    __table_args__ = (
        UniqueConstraint("run_id", "ts", name="uq_history_bar"),
        Index("ix_history_bar_run_ts", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    regime: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    permission: Mapped[str] = mapped_column(String(16), default="NO_TRADE")
    hmm_state: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hmm_probs_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rf_probs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_codes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    open: Mapped[float] = mapped_column(Float, default=0.0)
    high: Mapped[float] = mapped_column(Float, default=0.0)
    low: Mapped[float] = mapped_column(Float, default=0.0)
    close: Mapped[float] = mapped_column(Float, default=0.0)
    atr_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    adx_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1_trend_context: Mapped[float | None] = mapped_column(Float, nullable=True)
    m5_momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reference_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    di_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_channel_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_channel_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_displacement: Mapped[float | None] = mapped_column(Float, nullable=True)


class OutcomeEvaluation(Base):
    __tablename__ = "outcome_evaluations"
    __table_args__ = (
        UniqueConstraint("run_id", "ts", "horizon", name="uq_outcome_key"),
        Index("ix_outcome_run_ts", "run_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon: Mapped[int] = mapped_column(Integer)
    fwd_return: Mapped[float] = mapped_column(Float, default=0.0)
    mfe: Mapped[float] = mapped_column(Float, default=0.0)
    mae: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(8), default="FLAT")  # UP/DOWN/FLAT
    in_range: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reference_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)


class RegimeSegment(Base):
    __tablename__ = "regime_segments"
    __table_args__ = (Index("ix_segment_run_start", "run_id", "start_ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(16), default="XAUUSD")
    timeframe: Mapped[str] = mapped_column(String(8), default="M15")
    segment_index: Mapped[int] = mapped_column(Integer, default=0)
    regime: Mapped[str] = mapped_column(String(24))
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bar_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    start_price: Mapped[float] = mapped_column(Float, default=0.0)
    end_price: Mapped[float] = mapped_column(Float, default=0.0)
    high_price: Mapped[float] = mapped_column(Float, default=0.0)
    low_price: Mapped[float] = mapped_column(Float, default=0.0)
    net_change: Mapped[float] = mapped_column(Float, default=0.0)
    mfe: Mapped[float] = mapped_column(Float, default=0.0)
    mae: Mapped[float] = mapped_column(Float, default=0.0)
    atr_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    adx_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    hmm_probs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_mean: Mapped[float] = mapped_column(Float, default=0.0)
    model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    split_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)  # data_gap | None
    range_touches_high: Mapped[int] = mapped_column(Integer, default=0)
    range_touches_low: Mapped[int] = mapped_column(Integer, default=0)
