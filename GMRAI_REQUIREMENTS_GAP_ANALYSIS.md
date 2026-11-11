# GMRAI — Requirements Gap Analysis

> **Audit Deliverable 3 of 5**  
> **Project:** Gold Market Regime AI Intelligence (`GMRAI`)  
> **Scope:** Phase 3 (Feature Classification & Detailed Issue Specifications)

---

## 1. Feature Classification Matrix

Every GMRAI subsystem and feature is classified into one of five categories:
- **A.** Completed and verified
- **B.** Implemented but not verified
- **C.** Partially implemented
- **D.** Not implemented
- **E.** Implemented incorrectly and requiring correction

| ID | Feature / Subsystem | Category | Primary Module / Files | Status Summary |
|---|---|---|---|---|
| **F-01** | MT5 Closed-Candle Collector & Checkpointing | **A** | [`collector/mt5_client.py`](file:///Users/macos/Desktop/GMRAI/collector/mt5_client.py), [`collector/data_sync.py`](file:///Users/macos/Desktop/GMRAI/collector/data_sync.py) | Verified via 10 unit tests + 100k real `ftmo_mt5` candles in DB |
| **F-02** | Candle Ingestion API & OHLC Validation | **A** | [`services/ingestion.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/ingestion.py), [`routers/ingest.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/ingest.py) | Verified batch upsert, dedup, OHLC & future-ts guards |
| **F-03** | Causal Technical Indicators (`ATR`, `ADX`, `EMA`, `ER`) | **A** | [`ml/indicators.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/indicators.py) | Verified causal under random truncation (`test_features.py`) |
| **F-04** | Pure NumPy Causal HMM Forward Filter (`HmmFilter`) | **A** | [`ml/hmm_inference.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_inference.py) | Verified `<1e-5` parity with `hmmlearn` and zero look-ahead |
| **F-05** | Rule-Based Reference Regime Engine (`ref_v1`) | **A** | [`ml/reference_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/reference_engine.py) | Verified causal, deterministic, and separated from AI Regime |
| **F-06** | Forward Outcome Evaluation (`12, 48, 96` bars) | **A** | [`ml/outcome.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/outcome.py) | Verified evaluation-only forward returns, MFE/MAE, win rate |
| **F-07** | History Exports (`CSV`, `XLSX`, `PDF`) | **A** | [`ml/history_export.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/history_export.py) | Verified all 5 export scopes (`csv`/`xlsx` bars & segments, `pdf` report) |
| **F-08** | JWT Authentication & RBAC (`admin` vs `viewer`) | **A** | [`security/auth.py`](file:///Users/macos/Desktop/GMRAI/backend/app/security/auth.py), [`deps.py`](file:///Users/macos/Desktop/GMRAI/backend/app/deps.py) | Verified login, `/auth/me`, admin-only guards, SHA-256 ingest key |
| **F-09** | Windows Live FTMO Terminal IPC Connection | **B** | [`collector/collector.py`](file:///Users/macos/Desktop/GMRAI/collector/collector.py) | Previously ran on Windows (`579` sync logs in DB); not executable on macOS host |
| **F-10** | Docker Compose Multi-Container Stack (`postgres` + `nginx`) | **B** | [`docker-compose.yml`](file:///Users/macos/Desktop/GMRAI/docker-compose.yml), [`docker/`](file:///Users/macos/Desktop/GMRAI/docker) | Configs present; contains dual-scheduler collision (`GAP-11`) |
| **F-11** | Multi-TF Feature Alignment & Outlier Clipping | **C** | [`ml/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/features.py) | `asof_closed` aligns on M15 open instead of M15 close; `0.5–99.5%` clipping missing (`GAP-05`) |
| **F-12** | Early Trend Detection & Reason Code Mapping | **C** | [`ml/regime_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/regime_engine.py), [`frontend/lib/regime.ts`](file:///Users/macos/Desktop/GMRAI/frontend/lib/regime.ts) | Missing transition/H1 checks in early trend; 8 backend reason codes unmapped in UI (`GAP-07`) |
| **F-13** | Interactive Candlestick Chart Multi-TF Regime Overlay | **C** | [`TradingChartContainer.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/TradingChartContainer.tsx), [`market/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/market/page.tsx) | M15 regime bars not mapped by interval onto M5/H1 candles (`GAP-08`) |
| **F-14** | History Analyzer Global Filter Bar (`date` & `regimeMode`) | **C** | [`history/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/history/page.tsx), [`routers/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/history.py) | Filters only wired to 2 of 12 tabs (`Timeline` & `Segments`) (`GAP-09`) |
| **F-15** | Walk-Forward Backtest Persistence & Error Handling | **C** | [`services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py), [`ml/backtest_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/backtest_engine.py) | Missing `started_at`, `BacktestMetric` rows, fold details, and failure status update (`GAP-10`) |
| **F-16** | API Rate Limiting & Secret Hygiene | **C** | [`app/main.py`](file:///Users/macos/Desktop/GMRAI/backend/app/main.py), [`collector/.env`](file:///Users/macos/Desktop/GMRAI/collector/.env) | Only `/auth/login` rate-limited; missing `.gitignore`; plaintext creds (`GAP-12`) |
| **F-17** | Telegram Notification System | **D** | *Missing (`backend/app/services/telegram.py`)* | Zero implementation in backend, worker, or UI (`GAP-13`) |
| **F-18** | Persisted Feature Store (`/api/v1/features`) | **D** | [`routers/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/features.py), [`models.py`](file:///Users/macos/Desktop/GMRAI/backend/app/models/models.py) | `market_features` table is never written to (`0` rows) (`GAP-14`) |
| **F-19** | Live Regime Inference & State Persistence (`/regime/latest`) | **E** | [`services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py) | Steps `EngineState` and inserts duplicate DB rows on every HTTP GET poll (`GAP-01`) |
| **F-20** | Data Source Isolation (`ftmo_mt5` vs `synthetic_demo`) | **E** | [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py), [`prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py), [`market.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/market.py) | Interleaves demo ($1,910) and real MT5 ($4,500) candles (`GAP-02`) |
| **F-21** | Training Data Splits, Purge/Embargo & Model Freshness | **E** | [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py), [`ml/backtest_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/backtest_engine.py) | Missing 12-bar label embargo; `val` slice (15%) discarded; M5 limit mismatch (`GAP-03`) |
| **F-22** | RF Calibration & ONNX Export Pipeline | **E** | [`ml/rf_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/rf_model.py), [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py) | `CalibratedClassifierCV` crashes `.feature_importances_` and ONNX export (`GAP-04`) |
| **F-23** | HMM State-to-Regime Semantic Mapping | **E** | [`ml/hmm_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_model.py) | Rigid `ret1_mean > 0.25 * std` leaves approved HMM with zero `TREND_UP` states (`GAP-06`) |

---

## 2. Detailed Issue Specifications

### GAP-01 (Category E — Critical): Non-Idempotent Live Regime Prediction Corrupts Hysteresis & Floods `model_predictions`
- **File & Module**: [`backend/app/services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py#L64-L249) (`compute_latest_regime`)
- **Technical Problem**:
  `compute_latest_regime()` is invoked on every `GET /api/v1/regime/latest` and `GET /api/v1/stats/dashboard` request. It loads the last `ModelPrediction` row (`prev_pred`), restores `EngineState` (`up_confirm`, `down_confirm`, `exit_count`, `prev_up`, `prev_down`), calls `engine.step(combined)` on the latest closed M15 candle `feature_ts`, and inserts a new `ModelPrediction` row—even when `prev_pred.ts == feature_ts` and `prev_pred.model_version_id == hmm_version.id`.
- **Impact on the System**:
  1. **Corrupted Regime Hysteresis**: When `confirm_bars = 2` or `3`, polling `/regime/latest` twice within 30 seconds on the same M15 candle steps `up_confirm` multiple times on the same bar, falsely confirming a trend on a single bar!
  2. **Database Bloat & Redundant Compute**: Verified in `gmrai.db`: `model_predictions` has **2,267 rows across only 14 distinct M15 timestamps** (up to 331 duplicate rows for a single M15 candle), and reloads joblib/JSON artifacts from disk on every poll.
- **Proposed Solution**:
  1. Make `compute_latest_regime()` **idempotent per `(symbol, timeframe, feature_ts, hmm_version.id)`**: if `prev_pred` already matches `feature_ts` and `hmm_version.id`, return the cached prediction (updating only dynamic `data_age_minutes` and staleness degradation if the candle has since become stale) without re-stepping `EngineState` or inserting a duplicate row.
  2. When a new M15 bar closes (`feature_ts > prev_pred.ts`), restore `EngineState` from `prev_pred` (or replay warmup if a gap occurred) and advance `engine.step()` exactly once for the new bar.
  3. Add an in-memory artifact cache keyed by `(version_id, artifact_path)` so `joblib.load` and JSON parsing do not hit disk on every request.
- **Testing & Acceptance Criteria**:
  - Calling `GET /api/v1/regime/latest` 10 times with no new candles produces **at most 1 row** in `model_predictions` for that candle's `ts` and leaves `engine_state` (`up_confirm`, `down_confirm`) identical across all 10 calls.

---

### GAP-02 (Category E — Critical): Data Source Contamination (`synthetic_demo` Mixed with `ftmo_mt5`)
- **File & Module**:
  - [`backend/app/services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L46-L69) (`_load_candles`)
  - [`backend/app/services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py#L29-L55) (`_load_recent`)
  - [`backend/app/routers/market.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/market.py#L22-L67) (`get_candles`, `market_latest`)
  - [`backend/app/services/quality.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/quality.py#L27-L33) (`check_timeframe`)
  - [`backend/app/services/stats.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/stats.py#L27-L68) (`dashboard_stats`)
  - [`backend/app/services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py#L84-L95) (`submit_backtest`)
- **Technical Problem**:
  When `scripts/seed_demo_data.py` is run on a database that also receives real `ftmo_mt5` candles, `market_candles` contains both `source='synthetic_demo'` (prices ~$1,910 at off-grid timestamps `:04, :19, :34, :49`) and `source='ftmo_mt5'` (prices ~$4,500 at `:00, :15, :30, :45`). Only `services/history.py` filters by preferred source (`ftmo_mt5` > `mt5` > fallback). All other modules query `MarketCandle` without filtering by `source`.
- **Impact on the System**:
  1. **Corrupted Model Training**: Verified in `gmrai.db` Training Run #1 (`HMM-5s-20261110T172344`), where alternating `$1,910` and `$4,500` candles produced `ret1_mean = ±0.857` (+135% / -57% per bar!) and `duration_mean = 1.0`.
  2. **Corrupted Live Market Chart**: `GET /api/v1/candles` returns interleaved `$1,910` and `$4,500` candles between August and November 2026.
- **Proposed Solution**:
  1. Centralize source selection in a shared helper `resolve_preferred_source(db, symbol)` (preferring `ftmo_mt5` / `mt5` whenever real broker candles exist for the symbol, or accepting an explicit `source` filter).
  2. Apply `MarketCandle.source == preferred_source` consistently across `training.py`, `prediction.py`, `market.py`, `quality.py`, `stats.py`, `worker.py`, and `history.py`.
  3. Provide an admin utility / cleanup option to purge `synthetic_demo` rows once real `ftmo_mt5` data is present.
- **Testing & Acceptance Criteria**:
  - In a DB containing both `synthetic_demo` and `ftmo_mt5` candles, `/candles`, `/market/latest`, `/regime/latest`, `run_training`, `submit_backtest`, and `run_all_quality_checks` exclusively use `ftmo_mt5` candles and never interleave sources.

---

### GAP-03 (Category E — High): Look-Ahead Label Leakage, Unused `val` Slice, and Multi-TF Row Limit Mismatch in Training
- **File & Module**:
  - [`backend/app/services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L46-L155)
  - [`backend/app/ml/backtest_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/backtest_engine.py#L90-L105)
- **Technical Problem**:
  1. **Missing Purge/Embargo**: `run_training()` splits `n` rows via `chronological_indices(n, 0.70, 0.15)` and `sub_train_val_split(train, 0.2)` without calling `purge_train_indices(..., embargo=cfg.rf_horizon)`. Similarly, `backtest_engine.py:run_fold()` splits `subtrain, subval = sub_train_val_split(train, cfg.val_frac)` without purging `rf_horizon` bars between `subtrain` and `subval`.
  2. **Unused `val` Slice & Stale Final Model**: In `run_training()`, the `val` slice (`70%–85%`) from `chronological_indices` is never used! Instead, `train` (`0%–70%`) is split into `subtrain` (`0%–56%`) and `subval` (`56%–70%`), leaving `70%–85%` completely unused and training the saved model on only the first `56%` of the dataset.
  3. **Multi-TF Candle Limit Mismatch**: `_load_candles` uses `limit=10000` for M5, M15, and H1 alike. `10,000` M5 bars cover only `34.7 days`, whereas `10,000` M15 bars cover `104.1 days`, causing `build_features()` to drop ~66% of M15 bars when aligned solely against real M5 data.
- **Impact on the System**:
  - Look-ahead label leakage across split boundaries (`rf_horizon = 12` bars); 15% of data wasted; saved models are 44% stale at creation time; training only uses ~3,300 M15 bars instead of ~10,000 when M5 is capped at 10,000 rows.
- **Proposed Solution**:
  1. Use the three-way split (`train: 0..70%`, `val: 70..85%`, `test: 85..100%`) directly—applying `purge_train_indices(train, val[0], embargo=cfg.rf_horizon)` and `purge_train_indices(val, test[0], embargo=cfg.rf_horizon)`—so `train` is used for model fitting, `val` is used for RF hyperparameter tuning & threshold optimization, and `test` is used for OOS evaluation (eliminating the redundant `subtrain`/`subval` split that orphaned `val`).
  2. In `backtest_engine.py:run_fold()`, apply `purge_train_indices(subtrain, subval[0], embargo=cfg.rf_horizon)`.
  3. Scale `_load_candles` limits proportionally to timeframe period (`M15: limit`, `M5: limit * 3 + 500`, `H1: limit // 4 + 200`) in both `training.py` and `worker.py`.
- **Testing & Acceptance Criteria**:
  - Unit tests verify `max(train_idx) + rf_horizon <= min(val_idx)` and `max(val_idx) + rf_horizon <= min(test_idx)` in both `run_training()` and `run_fold()`.
  - With 10,000 M15 bars and 30,500 M5 bars, `build_features()` retains `>9,900` valid M15 feature rows.

---

### GAP-04 (Category E — High): `CalibratedClassifierCV` Breaks `.feature_importances_` and ONNX Export
- **File & Module**: [`backend/app/ml/rf_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/rf_model.py#L109-L133), [`backend/app/services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L156-L295), [`backend/app/ml/onnx_export.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/onnx_export.py)
- **Technical Problem**:
  When `maybe_calibrate()` improves Brier score on validation data, it returns a `CalibratedClassifierCV` wrapper. Subsequently:
  1. `training.py` line 290 accesses `rf_model.feature_importances_`, which raises `AttributeError` on `CalibratedClassifierCV`.
  2. `export_rf_to_onnx()` passes the model to `skl2onnx`, which fails or drops `zipmap=False` parity on isotonic `CalibratedClassifierCV`.
- **Impact on the System**:
  Any training run where isotonic calibration improves Brier score crashes with `AttributeError` before saving models!
- **Proposed Solution**:
  - Extract feature importances via a helper `get_rf_feature_importances(model)` that unwraps `model.estimator` (or averages across `calibrated_classifiers_`) when `model` is a `CalibratedClassifierCV`.
  - Keep the base uncalibrated `RandomForestClassifier` reference for ONNX export (or verify ONNX conversion and fallback cleanly to base `RandomForestClassifier` if ONNX conversion/parity fails on the calibrated wrapper).
- **Testing & Acceptance Criteria**:
  - A unit test forcing `maybe_calibrate()` to return a `CalibratedClassifierCV` completes `get_rf_feature_importances()`, `rf_probabilities()`, and `export_rf_to_onnx()` + `verify_onnx_parity()` without raising `AttributeError`.

---

### GAP-05 (Category C — Medium): Multi-TF `asof_closed` Timestamp Alignment & Missing Train Quantile Clipping
- **File & Module**: [`backend/app/ml/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/features.py#L78-L137)
- **Technical Problem**:
  1. `asof_closed()` joins `other["_close_time"]` (`open_ts + period_seconds`) against M15 open time `_t` instead of M15 close time `_t + 900s`. At M15 close `t + 15m`, the M5 bar at `t + 10m` (closing at `t + 15m`) and the H1 bar closing at `t + 15m` (when `t` is `:45`) are already closed and known, yet `asof_closed` ignores them and uses bars from 15 minutes earlier.
  2. `docs/DATA_PIPELINE.md` specifies clipping features to the `[0.5%, 99.5%]` train quantiles to prevent extreme outliers from distorting HMM Gaussian emissions, which is not implemented.
- **Impact on the System**:
  - 15-minute artificial lag on M5 timing features and H1 context features at the top of each hour.
  - Extreme outlier spikes can dominate HMM diagonal covariance estimates.
- **Proposed Solution**:
  1. In `build_features()`, pass M15 close times (`m15.index + pd.Timedelta(seconds=900)`) as the left join timestamp in `asof_closed()` so any M5 or H1 bar whose `_close_time <= m15_close_time` is matched (strictly causal at M15 bar close).
  2. Add train-set quantile clipping (`0.5%` to `99.5%`) in `fit_hmm_multistart()` / `HmmFilter` (storing `clip_low` and `clip_high` in the HMM artifact JSON for backward-compatible inference).
- **Testing & Acceptance Criteria**:
  - At M15 bar `10:45` (closing at `11:00`), `asof_closed` joins the H1 bar `10:00` (closed at `11:00`) and M5 bar `10:55` (closed at `11:00`), while never joining any bar closing at `> 11:00`.

---

### GAP-06 (Category E — High): HMM State Mapping Leaves Approved Models Without `TREND_UP` / `TREND_DOWN`
- **File & Module**: [`backend/app/ml/hmm_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_model.py#L139-L216) (`map_states_to_regimes`)
- **Technical Problem**:
  `map_states_to_regimes()` requires `ret1_mean > 0.25 * ret1_std` and `ema_slope_mean > 0.05` for `TREND_UP` (and symmetrically for `TREND_DOWN`). On 15-minute XAUUSD bars, `ret1_std` (`~0.0010`) is ~5× larger than single-bar drift `ret1_mean` (`~0.0002`), even in states with strong positive `ema_slope_mean` (`+0.54`), `di_gap_mean` (`+0.14`), and `efficiency_mean` (`0.51`).
- **Impact on the System**:
  - Verified in `gmrai.db`: The active approved HMM model (`id=1`) mapped State 3 (`ema_slope_mean=+0.538`, `di_gap_mean=+0.137`) to `UNKNOWN`, leaving the model with **no `TREND_UP` state** (`hmm_semantic["TREND_UP"] == 0.0` at all times).
- **Proposed Solution**:
  - Refine `map_states_to_regimes()` to use a composite directional trend score combining `ema_slope_mean`, `di_gap_mean`, `ret1_mean`, and `efficiency_mean` (and ensure that if an unassigned state has clear directional indicators `ema_slope_mean > 0.15` and `di_gap_mean > 0.05` with positive `ret1_mean`, it maps to `TREND_UP`, and symmetrically for `TREND_DOWN`).
- **Testing & Acceptance Criteria**:
  - Re-evaluating `map_states_to_regimes()` on the statistics of `HMM-5s-20261109T162021` (and on real `ftmo_mt5` XAUUSD training runs) assigns at least one `TREND_UP`, one `TREND_DOWN`, and one `SIDEWAYS` state when directional states exist.

---

### GAP-07 (Category C — Medium): Early Trend Heuristics & Unmapped Reason Codes in Frontend
- **File & Module**:
  - [`backend/app/ml/regime_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/regime_engine.py#L140-L235)
  - [`frontend/lib/regime.ts`](file:///Users/macos/Desktop/GMRAI/frontend/lib/regime.ts#L101-L115)
- **Technical Problem**:
  1. `RegimeEngine.step()` only checks `up >= theta_early` and `up - prev_up >= delta_early` for `EARLY_TREND_UP/DOWN`, ignoring HMM transition probability (`hmm_trans_up`/`down`) and `h1_trend_context` described in `docs/AI_MODEL_DESIGN.md`.
  2. `frontend/lib/regime.ts` is missing Vietnamese labels for `HYSTERESIS_HOLD`, `EXIT_BELOW_THRESHOLD`, `PENDING_CONFIRM`, `EARLY_DELTA_RISE`, `CONFIRM_1`, `CONFIRM_2`, `CONFIRM_3`, `NO_DATA`, `INSUFFICIENT_HISTORY`, `NO_APPROVED_MODEL`, and `H1_ALIGNED`.
- **Impact on the System**:
  - Raw English reason codes appear in the Vietnamese UI; Early Trend signals do not leverage H1 context or HMM transition probabilities.
- **Proposed Solution**:
  1. Enhance `RegimeEngine.step()` so `EARLY_TREND_UP/DOWN` also considers `hmm_trans_up`/`down` or `h1_trend_context` alignment and emits descriptive reason codes (`EARLY_DELTA_RISE`, `H1_ALIGNED`).
  2. Add all backend reason codes (including dynamic `CONFIRM_\d+` pattern matching) to `reasonCodeLabel()` in `frontend/lib/regime.ts`.
- **Testing & Acceptance Criteria**:
  - Every reason code emitted by `regime_engine.py` and `prediction.py` resolves to a human-readable Vietnamese label in `reasonCodeLabel()`.

---

### GAP-08 (Category C — Medium): Live Market Chart Multi-Timeframe Regime Band & HUD Alignment
- **File & Module**:
  - [`frontend/components/charts/TradingChart/useChartData.ts`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/useChartData.ts#L172-L202)
  - [`frontend/components/charts/TradingChart/TradingChartContainer.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/TradingChartContainer.tsx#L120-L155)
- **Technical Problem**:
  `useBarsIndex(bars)` indexes `HistoryBar` rows by exact M15 timestamp (`sec`). When the user switches the Live Market chart to `M5` (or `H1`), `barsByTime.get(sec)` only matches timestamps that fall on an exact M15 boundary, so hovering or clicking `:05`, `:10`, `:20`, `:25` M5 candles shows `—` for all regime metadata.
- **Impact on the System**:
  - Broken hover HUD and click-to-inspect modal on 67% of M5 candles in `/market`.
- **Proposed Solution**:
  - Update the bar lookup in `TradingChartContainer.tsx` / `useChartData.ts` to resolve the active M15 `HistoryBar` covering timestamp `sec` (i.e., `floor(sec / 900) * 900` for `M5`, or the most recent M15 bar within `[sec, sec + 3600)` for `H1`).
- **Testing & Acceptance Criteria**:
  - Hovering or clicking any M5, M15, or H1 candle within the history run's date range displays the corresponding AI Regime, Reference Regime, Confidence, and probabilities.

---

### GAP-09 (Category C — Medium): History Analyzer Global Date & Regime Mode Filters Ignored by 10 of 12 Tabs
- **File & Module**:
  - [`frontend/app/(app)/history/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/history/page.tsx#L318-L348)
  - [`backend/app/routers/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/history.py#L149-L265)
  - [`backend/app/services/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/history.py#L380-L530)
- **Technical Problem**:
  `HistoryFiltersBar` provides global `startDate`, `endDate`, and `regimeMode` (`ai` vs `reference`) filters, but `history/page.tsx` only passes `filters` to `TimelineTab` and `SegmentsTab`.
- **Impact on the System**:
  - Users filtering by date range or toggling `AI / Reference` mode on `/history` see unchanged full-year AI statistics on 10 of the 12 tabs.
- **Proposed Solution**:
  - Support optional `start: datetime | None = None`, `end: datetime | None = None`, and `regime_mode: str = "ai"` query parameters on the `/history/runs/{run_id}/stats/*` endpoints (filtering `segments_df` and `bars_df` before computing stats), and forward `filters` from `HistoryPage` to the statistical tabs (or clearly indicate filter scope on tabs that are inherently AI-vs-Reference comparisons).
- **Testing & Acceptance Criteria**:
  - Passing `?start=...&end=...` to `/history/runs/{id}/stats/duration`, `trends`, `sideways`, `transitions`, `periods`, etc. returns statistics restricted to that UTC window, and the frontend tabs reactive-fetch when `filters` change.

---

### GAP-10 (Category C — Medium): Incomplete `BacktestRun` Persistence & Stuck `"running"` Status on Job Failure
- **File & Module**: [`backend/app/services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py#L43-L120), [`backend/app/services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L103-L115)
- **Technical Problem**:
  1. `submit_backtest()` does not set `BacktestRun.started_at`, does not populate `BacktestMetric` rows, and does not update `BacktestRun.status = "failed"` if `run_walk_forward()` raises an exception.
  2. In `run_training()`, if `_load_candles` or `build_features` raises an exception before the `try:` block at line 116, `TrainingRun.status` remains `"running"` forever!
- **Impact on the System**:
  - Failed training or backtest jobs leave zombie `"running"` rows in the UI that cause the frontend to poll every 4 seconds indefinitely.
- **Proposed Solution**:
  - Wrap the entire body of `run_training()` (from line 104) and `submit_backtest()`'s inner `_job` in `try ... except Exception as e:` blocks that mark `TrainingRun.status = "failed"` / `BacktestRun.status = "failed"`, record `finished_at`, set `started_at` on `BacktestRun`, and populate `BacktestMetric` rows per fold/variant.
- **Testing & Acceptance Criteria**:
  - Triggering a training or backtest run with insufficient candles marks both `BackgroundJob` and `TrainingRun`/`BacktestRun` as `"failed"` with `finished_at` populated.

---

### GAP-11 (Category E — Medium): Dual Background Worker Scheduler in Docker Compose
- **File & Module**: [`backend/app/main.py`](file:///Users/macos/Desktop/GMRAI/backend/app/main.py#L27-L34), [`docker-compose.yml`](file:///Users/macos/Desktop/GMRAI/docker-compose.yml#L29-L64)
- **Technical Problem**:
  Both `backend` (`app.main:lifespan`) and `worker` (`app.worker_main:main`) call `worker.start_scheduler()`. In `docker-compose.yml`, both containers load `.env` where `GMRAI_AUTOMATION_ENABLED=true`.
- **Impact on the System**:
  - Duplicate concurrent quality checks and duplicate scheduled model retrains run in both containers simultaneously.
- **Proposed Solution**:
  - Set `GMRAI_AUTOMATION_ENABLED: "false"` on the `backend` web container in `docker-compose.yml` and `GMRAI_AUTOMATION_ENABLED: "true"` on the dedicated `worker` container (while keeping `true` as default for single-process local dev).
- **Testing & Acceptance Criteria**:
  - Inspecting `docker-compose.yml` and `app/main.py` confirms the periodic scheduler runs in at most one container in production deployments.

---

### GAP-12 (Category C — High): Security Hardening (Missing `.gitignore`, Plaintext Credentials, Rate Limiting)
- **File & Module**: [`.gitignore`](file:///Users/macos/Desktop/GMRAI/.gitignore) (missing), [`collector/.env`](file:///Users/macos/Desktop/GMRAI/collector/.env), [`backend/app/routers/ingest.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/ingest.py), [`frontend/app/login/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/login/page.tsx)
- **Technical Problem**:
  1. Repository root has no `.gitignore`, leaving `collector/.env` (containing FTMO credentials), `backend/gmrai.db`, `artifacts/`, and `.venv/` unprotected against accidental git commits.
  2. Stray duplicate files (`* 2.py`, `requirements 2.txt`, `requirements 3.txt`, `AI_MODEL_DESIGN 2.md`) clutter the workspace.
  3. Rate limiting (`@limiter.limit`) is only applied to `/auth/login`, not `/ingest/candles`.
- **Impact on the System**:
  - High risk of credential leakage and unthrottled ingestion requests.
- **Proposed Solution**:
  1. Create a comprehensive root `.gitignore` excluding `.env`, `collector/.env`, `*.db`, `artifacts/`, `checkpoints/`, `logs/`, `node_modules/`, `.next/`, `.venv/`.
  2. Apply `@limiter.limit` to `POST /api/v1/ingest/candles`.
  3. Remove stray Finder duplicate files (`* 2.*`, `* 3.*`) after user approval.
- **Testing & Acceptance Criteria**:
  - `git status --ignored` verifies `.env`, `collector/.env`, and `*.db` are ignored; rate limiter is active on `/auth/login` and `/ingest/candles`.

---

### GAP-13 (Category D — Medium): Telegram Notification Service Not Implemented
- **File & Module**: New module `backend/app/services/telegram.py`, [`backend/app/config.py`](file:///Users/macos/Desktop/GMRAI/backend/app/config.py), [`backend/app/routers/stats.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/stats.py) (system settings), [`frontend/app/(app)/settings/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/settings/page.tsx)
- **Technical Problem**:
  Phase 2 requires auditing Telegram notifications, which are currently completely unimplemented (`0` references in codebase).
- **Impact on the System**:
  - Operators receive no real-time push alerts when XAUUSD changes regime (`TREND_UP`, `TREND_DOWN`, `EARLY_TREND_*`, `HIGH_VOLATILITY`), when MT5 data becomes stale, or when background training/backtesting completes or fails.
- **Proposed Solution**:
  1. Add `telegram_bot_token: str = ""`, `telegram_chat_id: str = ""`, and `telegram_enabled: bool = False` to `Settings` in `backend/app/config.py` and `.env.example`.
  2. Implement `backend/app/services/telegram.py` with:
     - `send_telegram_message(text)` (using `httpx` with timeout and non-blocking error handling so notification failures never break inference or ingestion).
     - `notify_regime_change(prev_regime, new_regime, payload)` triggered ONLY when a genuinely new M15 candle causes a regime transition.
     - `notify_quality_stale(tf, report)` and `notify_job_completed(job_type, status, summary)`.
  3. Expose `GET /api/v1/system/telegram` status and `POST /api/v1/system/telegram/test` (admin-only) and add a Telegram status & test-button card in `frontend/app/(app)/settings/page.tsx`.
- **Testing & Acceptance Criteria**:
  - Unit tests mock `httpx.post` to verify regime-transition alerts fire once per transition, skip duplicate bars, format XAUUSD regime details clearly, and handle network errors gracefully without raising.

---

### GAP-14 (Category D — Low): `MarketFeature` Table & `GET /api/v1/features` Unpopulated
- **File & Module**: [`backend/app/routers/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/features.py), [`backend/app/services/ingestion.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/ingestion.py)
- **Technical Problem**:
  `GET /api/v1/features` queries the `market_features` table, which is never written to (`0` rows).
- **Impact on the System**:
  - Calling `GET /api/v1/features` always returns `{"total": 0, "features": []}`.
- **Proposed Solution**:
  - Update `GET /api/v1/features` so that if `market_features` has no stored rows (or when `compute_on_fly=true`), it computes and returns the causal multi-TF features from `build_features()` for the requested `symbol` and `limit` (and optionally persists/caches recent M15 feature rows during prediction/history runs).
- **Testing & Acceptance Criteria**:
  - `GET /api/v1/features?symbol=XAUUSD&timeframe=M15&limit=50` returns valid `v1` feature vectors matching `build_features()`.
