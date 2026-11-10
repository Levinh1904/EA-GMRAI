# GMRAI — Database Schema

## 1. Quy ước

- Engine: PostgreSQL 16 (production), SQLite (dev/test). SQLAlchemy 2.0 + Alembic migration.
- Timestamp: UTC, kiểu `DateTime(timezone=True)`.
- Primary key: integer autoincrement (đơn giản, index rõ ràng).
- Unique candle key: `(symbol, timeframe, ts)`.
- Dữ liệu lớn luôn qua pagination API; không trả toàn bộ lịch sử trong một response.

## 2. Bảng

### users
| cột | kiểu | ghi chú |
|---|---|---|
| id | PK | |
| username | str unique | |
| hashed_password | str | bcrypt |
| role | str | `admin` / `analyst` |
| is_active | bool | |
| created_at | tz | |

### api_keys
| cột | kiểu | ghi chú |
|---|---|---|
| id | PK | |
| name | str unique | tên collector |
| key_hash | str | sha256, không lưu raw |
| role | str | `ingest` |
| is_active | bool | |
| last_used_at | tz nullable | |
| created_at | tz | |

### market_candles
| cột | kiểu | ghi chú |
|---|---|---|
| id | PK | |
| symbol | str | `XAUUSD` |
| timeframe | str | `M5` / `M15` / `H1` |
| ts | tz | giờ mở nến, UTC |
| open, high, low, close | float | |
| tick_volume | int | |
| spread | int nullable | |
| real_volume | int nullable | |
| source | str | `ftmo_mt5` / `synthetic_demo` |
| created_at, updated_at | tz | |

Unique `(symbol, timeframe, ts)`; index `(symbol, timeframe, ts)`, `(timeframe, ts)`.

### data_sync_logs
collector_id, symbol, timeframe, started_at, finished_at, candles_received, candles_inserted, candles_updated, status (`ok`/`partial`/`error`), message.

### data_quality_reports
symbol, timeframe, checked_at, window_start, window_end, total_candles, missing_count, duplicate_count, gap_count, bad_candle_count, stale_ts (nến mới nhất), report_json (chi tiết từng gap), created_at.

### market_features
| cột | kiểu | ghi chú |
|---|---|---|
| id | PK | |
| symbol, timeframe | str | M15 |
| ts | tz | thời điểm đóng thanh M15 |
| feature_version | str | `v1` |
| ret1, ret4 | float nullable | |
| atr_ratio | float nullable | |
| ema_slope | float nullable | |
| efficiency_ratio | float nullable | |
| adx_norm | float nullable | |
| di_gap | float nullable | |
| h1_ema_slope, h1_atr_ratio, h1_adx_norm, h1_trend_context | float nullable | context H1 |
| m5_ret_short, m5_vol_ratio, m5_momentum | float nullable | timing M5 |

Unique `(symbol, timeframe, ts, feature_version)`.

### hmm_models
name, n_states, covariance_type, feature_version, hyperparams_json, dataset_range_json (train/val/test), scaler_params_json (mean/std theo feature), means/covars/transmat/startprob (lưu artifact + columns JSON để tái tạo), state_mapping_json (hidden → semantic + bằng chứng thống kê), train_log_likelihood, validation_log_likelihood, status, artifact_path, created_at.

### random_forest_models
name, feature_version, label_spec_json (horizon, thresholds), hyperparams_json, dataset_range_json, metrics_json (val/test), feature_importances_json, status, artifact_path (joblib + onnx), created_at.

### model_versions
model_type (`hmm`/`random_forest`), model_id, version (int), status (`training`/`validating`/`candidate`/`approved`/`rejected`/`archived`), metrics_json, artifact_path, created_at.

### model_predictions
model_version_id, symbol, timeframe, ts, regime, confidence, probabilities_json (HMM posterior + RF probs), components_json, reason_codes_json, expiry_ts, permission (`BUY_ONLY`/`SELL_ONLY`/`NO_TRADE`), data_timestamp, created_at. Index `(symbol, timeframe, ts)`.

### training_runs
model_type, params_json, dataset_json, feature_version, status (`pending`/`running`/`done`/`failed`), metrics_json, error, log_path, started_at, finished_at.

### backtest_runs
name, config_json (window mode, sizes, thresholds, costs), hmm_model_version_id, rf_model_version_id, status, metrics_json, report_path, started_at, finished_at.

### backtest_metrics
backtest_run_id, metric_name, value (float), meta_json.

### background_jobs
job_type, status, params_json, result_json, error, started_at, finished_at.

### system_logs
level, component, message, meta_json, created_at. Index `(created_at)`.

### regime_history_runs (Historical Analyzer)
symbol, timeframe, hmm_model_version_id, rf_model_version_id, feature_version,
data_source (`ftmo_mt5`/`synthetic_demo` — không trộn nguồn), status
(pending/running/done/failed), config_json, bar_count, segment_count,
data_start, data_end, error, timestamps.

### regime_history_bars
run_id, ts, regime, confidence, permission, hmm_state, hmm_probs_json,
rf_probs_json, reason_codes_json, open/high/low/close, atr_ratio, adx_norm,
efficiency_ratio, h1_trend_context, m5_momentum.
Unique `(run_id, ts)`; index `(run_id, ts)`.

### regime_segments
run_id, segment_index, regime, start_ts, end_ts, bar_count, duration_minutes,
start/end/high/low price, net_change, mfe, mae, atr_mean, adx_mean,
efficiency_mean, hmm_probs_json, confidence_mean, model_version_id,
split_reason (`data_gap`|null), range_touches_high/low.
Index `(run_id, start_ts)`.

## 3. Migration

- Alembic `backend/alembic`; migration đầu `0001_initial`.
- Downgrade được hỗ trợ (rollback khi phù hợp).
- Trước migration quan trọng trên production: backup DB (pg_dump) — xem OPERATIONS_GUIDE.
