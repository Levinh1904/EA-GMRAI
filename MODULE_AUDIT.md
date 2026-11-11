# GMRAI — Technical Module Audit Report

> **Audit Deliverable 2 of 5**  
> **Project:** Gold Market Regime AI Intelligence (`GMRAI`)  
> **Scope:** Phase 2 (Technical Audit across all 14 required domains + Verified Test Results)

---

## 1. Verified Test & Build Execution Summary

Before documenting module-level findings, we executed the existing backend test suite, frontend TypeScript compiler check, and read-only SQLite database inspection:

| Verification Check | Command | Result | Details |
|---|---|---|---|
| Backend Pytest Suite | `pytest backend/tests -v` | **PASS (115/115)** | 115 passed, 10 pandas timezone warnings in `96.39s` |
| Frontend TypeScript | `tsc --noEmit -p frontend/tsconfig.json` | **PASS (0 errors)** | Strict TypeScript 5.6 compilation clean |
| Live SQLite DB (`gmrai.db`) | Read-only SQLite inspection | **INSPECTED** | 137,957 `market_candles` (mixed `ftmo_mt5` & `synthetic_demo`), 4 `model_versions`, 3 `regime_history_runs`, 2,267 `model_predictions` |

---

## 2. Audit by Technical Domain (14 Areas)

### 2.1 Frontend Architecture and UI/UX
- **Files Inspected**: [`frontend/app/`](file:///Users/macos/Desktop/GMRAI/frontend/app), [`frontend/components/`](file:///Users/macos/Desktop/GMRAI/frontend/components), [`frontend/lib/`](file:///Users/macos/Desktop/GMRAI/frontend/lib)
- **What Works (Verified)**:
  - Next.js 15 App Router structure with 10 authenticated routes (`Overview`, `Live Market`, `AI Regime`, `History`, `Training`, `Backtesting`, `Model Compare`, `Model Registry`, `Data Center`, `Settings`) + `/login`.
  - [`AuthProvider.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/AuthProvider.tsx) manages JWT Bearer persistence in `localStorage`, validates session via `GET /api/v1/auth/me`, and enforces role-based UI controls (`isAdmin`).
  - [`AppShell.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/layout/AppShell.tsx) provides a responsive collapsible sidebar, live status topbar, `synthetic_demo` warning banner, and research disclaimer footer.
- **Defects & Gaps Found**:
  1. **Unmapped Backend Reason Codes in [`frontend/lib/regime.ts`](file:///Users/macos/Desktop/GMRAI/frontend/lib/regime.ts#L101-L115)**: [`reasonCodeLabel()`](file:///Users/macos/Desktop/GMRAI/frontend/lib/regime.ts#L101-L115) maps only 7 codes (`RF_HMM_DIVERGE`, `RF_HMM_AGREE`, `HIGH_VOL_FILTER`, `EARLY_SIGNAL`, `LOW_CONFIDENCE`, `STALE_DATA`, `TRANSITION_FILTER`), whereas [`regime_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/regime_engine.py#L140-L230) and [`prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py#L84-L162) actually emit `HYSTERESIS_HOLD`, `EXIT_BELOW_THRESHOLD`, `CONFIRM_2` (and `CONFIRM_{k}`), `PENDING_CONFIRM`, `EARLY_DELTA_RISE`, `NO_DATA`, `INSUFFICIENT_HISTORY`, and `NO_APPROVED_MODEL`. Unmapped codes fall back to raw English uppercase strings in a Vietnamese UI.
  2. **Global History Filters Disconnected on 10 of 12 Tabs ([`frontend/app/(app)/history/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/history/page.tsx#L318-L348))**: [`HistoryFiltersBar.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/history/HistoryFiltersBar.tsx) renders global `startDate`, `endDate`, and `regimeMode` (`AI` vs. `Reference`) controls at the top of `/history`. However, `filters` is only passed to `TimelineTab` and `SegmentsTab`. Switching `regimeMode` to `Reference` or setting a UTC date range has **zero effect** on `OverviewTab`, `TrendsTab`, `SidewaysTab`, `EarlyTrendTab`, `TransitionsTab`, `MultiTfTab`, `CompareTab`, `ReferenceCompareTab`, `OutcomesTab`, or `ReportsTab`.
  3. **Redundant Polling Triggers Backend State Mutation**: `TopBar`, `DemoBanner`, `Footer` (all mounted in [`AppShell.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/layout/AppShell.tsx)), plus `OverviewPage`, `MarketPage`, and `RegimePage` poll `/regime/latest` and `/stats/dashboard` every 30s. Because `/stats/dashboard` also calls `compute_latest_regime()` on the backend, every page load triggers multiple concurrent `compute_latest_regime()` executions.
  4. **Hardcoded Default Admin Credentials in Login Form ([`frontend/app/login/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/login/page.tsx#L12-L13))**: `useState('admin')` and `useState('admin-change-me')` are pre-filled and displayed in plain text below the login button.

---

### 2.2 Interactive Candlestick Chart Functionality
- **Files Inspected**: [`TradingChartContainer.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/TradingChartContainer.tsx), [`useChartData.ts`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/useChartData.ts), [`chartToolbar.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/chartToolbar.tsx), [`chartOverlays.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/TradingChart/chartOverlays.tsx), [`CandlestickChart.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/CandlestickChart.tsx)
- **What Works (Verified)**:
  - Built on `lightweight-charts` v5.3 (`createChart`, `CandlestickSeries`, `HistogramSeries`, `LineSeries`).
  - Supports timeframe switching (`M5`, `M15`, `H1`), range presets (`1D`, `3D`, `1W`, `1M`, `3M`, `6M`, `1Y`, `ALL`), zoom in/out/reset, auto-scale, grid/crosshair toggles, volume toggle, client-side `EMA 20` & `EMA 50`, AI regime background bands, Reference regime background bands, OHLC + Regime hover HUD, click-to-inspect modal, and automatic leftward pagination (`5,000` bars per batch when scrolling within 80 bars of the left edge).
- **Defects & Gaps Found**:
  1. **M15 History Regime Bands Overlaid onto M5/H1 Without Timeframe Alignment ([`market/page.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/app/(app)/market/page.tsx#L66-L86))**: `doneRun` is always an `M15` history run, and `barsByTime` indexes M15 bar timestamps (`:00, :15, :30, :45`). When the user switches the chart to `M5`, 2 out of every 3 M5 candles (`:05, :10, :20, :25...`) have no exact timestamp match in `barsByTime`, so hovering or clicking those M5 candles shows `—` for AI Regime, Reference Regime, Confidence, HMM Posterior, and RF Probabilities.
  2. **Mixed `synthetic_demo` and `ftmo_mt5` Candles Corrupt Chart Series ([`routers/market.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/market.py#L22-L67))**: `GET /api/v1/candles` queries `MarketCandle` without filtering by `source`. In `gmrai.db`, between `2026-08-07` and `2026-11-09`, `synthetic_demo` candles (~$1,910 at `:04, :19, :34, :49`) and `ftmo_mt5` candles (~$4,500 at `:00, :15, :30, :45`) are interleaved, creating vertical $2,500 spikes on every bar in that date range!
  3. **Unused Legacy Component**: [`CandlestickChart.tsx`](file:///Users/macos/Desktop/GMRAI/frontend/components/charts/CandlestickChart.tsx) (Plotly candlestick chart) is dead code superseded by `TradingChartContainer.tsx`.

---

### 2.3 Backend Architecture and API
- **Files Inspected**: [`app/main.py`](file:///Users/macos/Desktop/GMRAI/backend/app/main.py), [`app/routers/`](file:///Users/macos/Desktop/GMRAI/backend/app/routers), [`app/services/`](file:///Users/macos/Desktop/GMRAI/backend/app/services), [`app/models/models.py`](file:///Users/macos/Desktop/GMRAI/backend/app/models/models.py)
- **What Works (Verified)**:
  - All 12 routers mount cleanly under `/api/v1` and pass 16 API integration tests (`test_api.py`) and 7 History API tests (`test_history_api.py`).
  - Role-based access control (`require_admin` vs `get_current_user`) properly guards state-changing endpoints (`POST /training/run`, `POST /backtests`, `POST /models/{id}/status`, `POST /quality/run`, `POST /history/run`).
- **Defects & Gaps Found**:
  1. **`GET /api/v1/features` Always Returns Empty ([`routers/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/features.py#L14-L42))**: Queries `MarketFeature`, which is never populated anywhere in the codebase (`0` rows in `gmrai.db`).
  2. **`BacktestRun` & `TrainingRun` Error Handling and Missing `BacktestMetric` Population ([`services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py#L80-L120))**:
     - `submit_backtest()` never sets `BacktestRun.started_at` (verified in `gmrai.db`: `started_at` is `None` for Backtest #1), never populates `BacktestMetric` rows (`0` rows in `gmrai.db`), never sets `hmm_model_version_id` / `rf_model_version_id` / `report_path`, and discards per-fold `folds` results.
     - If `run_walk_forward()` raises an exception, `BacktestRun.status` stays `"running"` permanently because `worker.run_job()` only catches exceptions at the `BackgroundJob` level.

---

### 2.4 Python Data Processing Pipeline
- **Files Inspected**: [`services/ingestion.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/ingestion.py), [`services/quality.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/quality.py), [`services/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/history.py)
- **What Works (Verified)**:
  - [`validate_candle()`](file:///Users/macos/Desktop/GMRAI/backend/app/services/ingestion.py#L22-L43) enforces positive OHLC, `high >= max(open, close)`, `low <= min(open, close)`, non-negative volume/spread, and rejects timestamps more than 5 minutes in the future.
  - [`quality.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/quality.py) detects weekend-aware missing bars, gaps, bad OHLC candles, and timeframe staleness.
- **Defects & Gaps Found**:
  1. **Critical Data Source Contamination (`synthetic_demo` + `ftmo_mt5`)**:
     - Only [`services/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/history.py#L31-L55) implements `_choose_source()` (`PREFERRED_SOURCES = ("ftmo_mt5", "mt5")`) to filter `MarketCandle.source == chosen_source`.
     - [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L46-L69), [`services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py#L29-L55), [`services/quality.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/quality.py#L27-L33), [`services/stats.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/stats.py#L27-L68), [`services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py#L84-L95), and [`routers/market.py`](file:///Users/macos/Desktop/GMRAI/backend/app/routers/market.py#L22-L67) query `MarketCandle` **without** filtering by `source`.
     - **Verified Impact in `gmrai.db`**: Training Run #1 (`2026-11-10`) loaded interleaved `synthetic_demo` and `ftmo_mt5` candles, resulting in `ret1_mean = +0.857` and `-0.857` (`duration_mean = 1.0`) in `HMM-5s-20261110T172344`!
  2. **Mismatched Multi-Timeframe Candle Limit in [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L105-L107) and [`services/worker.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/worker.py#L84-L95)**:
     - `_load_candles(db, symbol, tf, limit=10000)` loads at most `10,000` rows for each timeframe (`M5`, `M15`, `H1`).
     - `10,000` M15 bars span **104 days**, whereas `10,000` M5 bars span only **34.7 days**! When `build_features()` joins M5 onto M15 via `pd.merge_asof(..., direction="backward")`, all M15 bars older than 34.7 days either get `NaN` (if before the earliest M5 bar, dropping 66% of the M15 dataset!) or get forward-filled with a single stale M5 bar across months if an older demo M5 bar exists! M5 limit must be at least `3 * limit_m15` (e.g., `35,000` for `10,000` M15 bars, or time-range aligned).

---

### 2.5 Random Forest Model
- **Files Inspected**: [`ml/rf_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/rf_model.py), [`ml/labels.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/labels.py)
- **What Works (Verified)**:
  - 28-feature matrix (`14` market features + `5` HMM posteriors + `5` one-hot HMM states + `hmm_max_prob` + `hmm_entropy` + `hmm_delta1` + `hmm_delta3` + `hmm_trans_up` + `hmm_trans_down`).
  - Uses `class_weight="balanced_subsample"` and tunes hyperparameters (`n_estimators`, `max_depth`, `min_samples_leaf`) on validation Macro F1.
- **Defects & Gaps Found**:
  1. **`maybe_calibrate()` Crash & ONNX Incompatibility ([`ml/rf_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/rf_model.py#L109-L133), [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L156-L290))**:
     - If [`maybe_calibrate()`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/rf_model.py#L109-L133) finds that `CalibratedClassifierCV(estimator=model, method="isotonic", cv=3)` improves Brier score, it returns the `CalibratedClassifierCV` instance instead of `RandomForestClassifier`.
     - In [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L290), `rf_model.feature_importances_` is accessed unconditionally — `CalibratedClassifierCV` does **not** have `.feature_importances_`, raising `AttributeError: 'CalibratedClassifierCV' object has no attribute 'feature_importances_'`!
     - Furthermore, `CalibratedClassifierCV(cv=3)` uses `StratifiedKFold(shuffle=False)` internally on time-series validation data without embargo, and `skl2onnx` fails to export isotonic `CalibratedClassifierCV` with `zipmap=False` in many configurations.
  2. **Arithmetic Price Difference Used Instead of Log Return in [`ml/labels.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/labels.py#L14-L35)**:
     - [`docs/AI_MODEL_DESIGN.md`](file:///Users/macos/Desktop/GMRAI/docs/AI_MODEL_DESIGN.md#L58-L62) states `fwd_ret(t) = log(close[t+h] / close[t])`, whereas [`labels.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/labels.py#L26) computes `fwd = close.shift(-horizon) - close` compared against `±up_threshold_atr * atr14`. Note: comparing dollar price change `close[t+h] - close[t]` to dollar `ATR14(t)` is actually dimensionally consistent (both in USD), whereas comparing log return to dollar ATR would be dimensionally invalid; the documentation formula in `docs/AI_MODEL_DESIGN.md` should be updated to match `close[t+h] - close[t]`.

---

### 2.6 Hidden Markov Model (HMM)
- **Files Inspected**: [`ml/hmm_inference.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_inference.py), [`ml/hmm_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_model.py)
- **What Works (Verified)**:
  - [`HmmFilter`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_inference.py#L14-L98) implements exact causal forward recursion $\alpha_t(j) \propto \big(\sum_i \alpha_{t-1}(i) A_{ij}\big) \mathcal{N}(x_t; \mu_j, \text{diag}(\sigma_j^2))$ in log-space (`_logsumexp`) without future Viterbi smoothing.
  - Verified parity (`< 1e-5`) against `hmmlearn` on single-step and initial distributions (`test_hmm_inference.py`).
- **Defects & Gaps Found**:
  1. **`map_states_to_regimes()` Can Leave Approved HMM Models Without `TREND_UP` or `TREND_DOWN` ([`ml/hmm_model.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/hmm_model.py#L139-L216))**:
     - The rule `s["ret1_mean"] > 0.25 * max(s["ret1_std"], 1e-6) and s["ema_slope_mean"] > 0.05` is overly rigid for 15-minute financial returns where single-bar SNR (`mean / std`) is typically `0.05–0.20` even during strong trends (`ema_slope_mean = +0.54`, `adx_mean = 0.37`, `di_gap_mean = +0.14`).
     - **Verified in `gmrai.db`**: In the currently approved `HMM-5s-20261109T162021` (`model_version_id=1`), State 3 (`ema_slope_mean = +0.538`, `efficiency_mean = 0.512`, `di_gap_mean = +0.137`, `ret1_mean = +0.000195`, `ret1_std = 0.000996`) failed `0.000195 > 0.25 * 0.000996` (`0.000249`) and was mapped to `UNKNOWN`! Consequently, the active production HMM model has **0 states mapped to `TREND_UP`**, so `hmm_semantic["TREND_UP"]` is permanently `0.0`!

---

### 2.7 AI Regime Detection (`RegimeEngine`)
- **Files Inspected**: [`ml/regime_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/regime_engine.py), [`services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py)
- **What Works (Verified)**:
  - Combines HMM semantic probabilities and RF class probabilities via `weight_hmm`, applies entry threshold `theta_enter`, exit hysteresis `theta_exit`, N-bar confirmation `confirm_bars`, high-volatility/transition filters, and maps regimes to research permissions (`BUY_ONLY`, `SELL_ONLY`, `NO_TRADE`).
- **Defects & Gaps Found**:
  1. **Critical Bug — Non-Idempotent Live Stepping Corrupts Hysteresis & Floods DB ([`services/prediction.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/prediction.py#L165-L236))**:
     - Every call to `compute_latest_regime()` loads the most recent `ModelPrediction` row (`prev_pred`), restores `EngineState` from `prev_pred.probabilities_json["engine_state"]`, calls `engine.step(combined)` on the latest M15 bar `feature_ts`, and inserts a **new** `ModelPrediction` row—**without checking if `prev_pred.ts == feature_ts`!**
     - Because `feature_ts` only changes once every 15 minutes while the UI polls every 30 seconds, `engine.step()` is called ~30–100 times on the exact same candle! A single bar with `up >= theta_enter` steps `up_confirm` from `1 → 2 → 3` within seconds, bypassing multi-bar confirmation (`confirm_bars`) and inserting thousands of duplicate rows (verified in `gmrai.db`: 2,267 rows for 14 timestamps).
  2. **Simplified Early Trend Detection vs. Design Spec ([`ml/regime_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/regime_engine.py#L202-L215))**:
     - [`docs/AI_MODEL_DESIGN.md`](file:///Users/macos/Desktop/GMRAI/docs/AI_MODEL_DESIGN.md#L53) specifies that `EARLY_TREND_UP/DOWN` should incorporate filtered posterior, HMM transition probability into trend (`hmm_trans_up`/`down`), posterior delta, H1 trend context, and trend features. Currently, `RegimeEngine.step()` only checks `up >= theta_early` and `up - prev_up >= delta_early`.

---

### 2.8 Reference Regime Calculation (`reference_engine.py`)
- **Files Inspected**: [`ml/reference_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/reference_engine.py), [`tests/test_reference_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/tests/test_reference_engine.py)
- **What Works (Verified)**:
  - Deterministic, causal rule-based classifier (`REFERENCE_VERSION = "ref_v1"`) using `ADX`, `DI gap`, `EMA slope`, `Efficiency Ratio`, `ATR ratio`, `H1 trend context`, and causal `channel_lookback=20` high/low range width.
  - Strictly separated from AI Regime predictions in database columns (`RegimeHistoryBar.reference_regime` vs `RegimeHistoryBar.regime`), API responses, and UI overlays.
  - Truncation causality verified by `test_reference_is_causal_under_truncation`.

---

### 2.9 Feature Engineering (`indicators.py`, `features.py`)
- **Files Inspected**: [`ml/indicators.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/indicators.py), [`ml/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/features.py), [`tests/test_features.py`](file:///Users/macos/Desktop/GMRAI/backend/tests/test_features.py)
- **What Works (Verified)**:
  - All 14 features are strictly causal (verified by `test_no_lookahead_random_truncation`).
- **Defects & Gaps Found**:
  1. **M15 Open Timestamp Used Instead of Close Timestamp in `asof_closed` ([`ml/features.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/features.py#L78-L132))**:
     - In `build_features()`, `df_m15` is indexed by M15 **open** time `t` (so the bar closes at `t + 900s`).
     - `asof_closed(m15, compute_m5_features(df_m5), 300, M5_FEATURES)` sets `other["_close_time"] = other.index + 300s`, but matches against `left_on="_t"` where `_t` is M15 **open** time `t` rather than M15 **close** time `t + 900s`!
     - Impact: At M15 bar `10:00` (which closes at `10:15`), `asof_closed` joins the M5 bar that closed at `10:00` (open `09:55`) instead of the M5 bar that closed at `10:15` (open `10:10`), introducing an unnecessary 15-minute lag in M5 timing features and up to a 15-minute lag on H1 features when `t` is `:45` (`10:45` M15 closes at `11:00`, when the `10:00–11:00` H1 bar has already closed!).
  2. **Missing Train Quantile Outlier Clipping (`0.5–99.5%`)**:
     - Documented in [`docs/DATA_PIPELINE.md`](file:///Users/macos/Desktop/GMRAI/docs/DATA_PIPELINE.md#L64) (*"Outlier: clip theo phân vị 0.5–99.5 của train"*), but not implemented in `features.py` or `hmm_model.py`.

---

### 2.10 Data Leakage and Look-Ahead Bias Audit
- **Files Inspected**: [`ml/splits.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/splits.py), [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py), [`ml/backtest_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/backtest_engine.py), [`ml/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/history.py)
- **Leakage Issues Identified**:
  1. **Missing Embargo/Purge in `run_training()` ([`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L118-L125))**:
     - `labels` at index `t` use `close[t + 12] - close[t]` (`rf_horizon = 12`).
     - Although `splits.py` defines `purge_train_indices(test_start, embargo)`, `run_training()` calls `chronological_indices(n, cfg.train_frac, cfg.val_frac)` and `sub_train_val_split(train, 0.2)` **without calling `purge_train_indices`!**
     - The last 12 bars of `subtrain` use future prices from `subval` in their RF target labels, and the boundary between `subval`/`val` and `test` has no embargo.
  2. **Missing Embargo Between `subtrain` and `subval` in Walk-Forward Backtest ([`ml/backtest_engine.py`](file:///Users/macos/Desktop/GMRAI/backend/app/ml/backtest_engine.py#L92-L93))**:
     - While `walk_forward_folds()` enforces `embargo=12` between `train` and `test`, inside `run_fold()` line 92, `subtrain, subval = sub_train_val_split(train, cfg.val_frac)` does **not** purge the last `rf_horizon` bars of `subtrain` before `subval`.
  3. **In-Sample Historical Replay Overlap ([`services/history.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/history.py#L114-L163))**:
     - `execute_history_run()` runs the currently approved HMM + RF models over the entire 1-year M15 history (`23,552` bars). Because the approved models were trained on the first 56%–70% of that same 1-year window, the first portion of a History Run is **in-sample** while the tail is **out-of-sample**, without recording the model's `train_end_ts` cutoff in `RegimeHistoryRun` metadata or UI notices.

---

### 2.11 Model Training and Validation
- **Files Inspected**: [`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py)
- **Defects & Gaps Found**:
  1. **15% Validation Slice (`val`) Completely Discarded & Model Staleness Gap ([`services/training.py`](file:///Users/macos/Desktop/GMRAI/backend/app/services/training.py#L118-L148))**:
     - `chronological_indices(n, 0.70, 0.15)` creates `train` (`0%–70%`), `val` (`70%–85%`), and `test` (`85%–100%`).
     - Line 121 then splits `train` into `subtrain` (`0%–56%`) and `subval` (`56%–70%`), fits HMM and RF on `subtrain`, tunes on `subval`, and evaluates on `test` (`85%–100%`).
     - The `val` slice (`70%–85%`, 1,500 M15 bars ≈ 15.6 days) is **never used anywhere**! Moreover, the saved production artifacts (`HMM` and `RF`) are only fit on the oldest `56%` of the data, leaving them **44% stale** (`~45 days` behind the latest bar) at the moment training finishes!

---

### 2.12 MT5 Integration (`collector/`)
- **Files Inspected**: [`collector/mt5_client.py`](file:///Users/macos/Desktop/GMRAI/collector/mt5_client.py), [`collector/data_sync.py`](file:///Users/macos/Desktop/GMRAI/collector/data_sync.py), [`collector/api_client.py`](file:///Users/macos/Desktop/GMRAI/collector/api_client.py), [`collector/collector.py`](file:///Users/macos/Desktop/GMRAI/collector/collector.py)
- **What Works (Verified)**:
  - Clean separation of MT5 IPC (`MT5Client`), chunked synchronization with checkpointing (`DataSynchronizer`), and retry-capable HTTP batching (`IngestionApiClient`).
  - `last_closed_bar_open()` mathematically guarantees forming bars are never ingested.
  - 10 unit tests in [`test_collector_logic.py`](file:///Users/macos/Desktop/GMRAI/backend/tests/test_collector_logic.py) pass on macOS without requiring the Windows `MetaTrader5` binary.
- **Defects & Gaps Found**:
  - [`collector/.env`](file:///Users/macos/Desktop/GMRAI/collector/.env) exists on disk with plaintext FTMO Demo credentials and no root `.gitignore` to prevent accidental commit.

---

### 2.13 Telegram Notifications
- **Audit Status**: **NOT IMPLEMENTED (`D`)**
- **Findings**:
  - A full-codebase search across `backend/`, `collector/`, `frontend/`, and `docs/` confirmed **zero references or implementations** of Telegram notifications (`telegram`, `bot_token`, `chat_id`).
  - For a production GMRAI system monitoring XAUUSD regimes on a VPS, a dedicated `TelegramNotificationService` is needed to alert operators on:
    1. Confirmed AI Regime transitions (e.g., `SIDEWAYS → TREND_UP` / `TREND_DOWN`, `EARLY_TREND_*` warnings, `HIGH_VOLATILITY` alerts) with confidence, permission, and reason codes.
    2. Data quality & staleness alerts (when collector sync stops or M5/M15/H1 becomes stale).
    3. Automated model training / walk-forward backtest completion or failure.

---

### 2.14 VPS Deployment and Security
- **Files Inspected**: [`docker-compose.yml`](file:///Users/macos/Desktop/GMRAI/docker-compose.yml), [`docker/Dockerfile.backend`](file:///Users/macos/Desktop/GMRAI/docker/Dockerfile.backend), [`docker/Dockerfile.frontend`](file:///Users/macos/Desktop/GMRAI/docker/Dockerfile.frontend), [`docker/nginx.conf`](file:///Users/macos/Desktop/GMRAI/docker/nginx.conf), [`.env.example`](file:///Users/macos/Desktop/GMRAI/.env.example)
- **Defects & Gaps Found**:
  1. **Dual Background Scheduler Execution in Docker Compose**: Both `backend` (`uvicorn app.main:app`) and `worker` (`python -m app.worker_main`) start `worker.start_scheduler()` because `GMRAI_AUTOMATION_ENABLED=true` is shared in `.env.example`.
  2. **HTTP-Only Nginx Config ([`docker/nginx.conf`](file:///Users/macos/Desktop/GMRAI/docker/nginx.conf))**: Listens on port `80` only with no TLS/HTTPS block, HSTS header, or `client_max_body_size` tuning for large candle batch ingestions.
  3. **Missing `.gitignore`**: No `.gitignore` file at repository root to protect `.env`, `collector/.env`, `*.db`, `collector/checkpoints/`, and `artifacts/`.
