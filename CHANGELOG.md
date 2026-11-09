# Changelog

## [0.1.0] — 2026-11-09

### M1 — Architecture & skeleton
- Git repo, cấu trúc monorepo (backend/collector/frontend/docs/scripts/docker).
- 9 tài liệu thiết kế trong docs/.

### M2 — FTMO MT5 Data Collector (Windows)
- `collector/`: collector.py, config.py, mt5_client.py, data_sync.py,
  api_client.py, logger.py, requirements.txt, .env.example, README.
- Chỉ gửi nến đã đóng; checkpoint; resync 50 nến; backfill `--backfill N`;
  tự phục hồi MT5; client-side gap/bad-bar check; KHÔNG chế dữ liệu thiếu.
- Logic có unit test chạy mọi nền tảng (test_collector_logic.py).
- Chưa test tích hợp MT5 thật (cần Windows + FTMO — blocker đã ghi nhận).

### M3 — Backend & Database
- FastAPI + SQLAlchemy 2.0 + Alembic (migration up/down verified).
- 15 bảng: candles, sync logs, quality reports, features, HMM/RF models,
  model versions, predictions, training runs, backtest runs/metrics,
  background jobs, system logs, users, api_keys.
- Auth: JWT (PyJWT) + bcrypt, roles admin/analyst, API key cho ingestion,
  rate limiting (slowapi), CORS.

### M4 — Feature engineering
- M15: ret1, ret4, atr_ratio, ema_slope, efficiency_ratio, adx_norm, di_gap.
- H1 context + M5 timing nối qua asof CLOSED bars only; feature version v1;
  NaN/Inf xử lý; no-lookahead (test truncation invariance).

### M5 — HMM Regime Detection
- GaussianHMM 5 states, diag covariance, multistart (10 seeds).
- Semantic mapping qua thống kê tập train (không ép gán; UNKNOWN khi mơ hồ).
- **Phát hiện & khóa bẫy lookahead**: hmmlearn `predict_proba()` là smoothed
  (dùng tương lai) — pipeline chỉ dùng `HmmFilter` NumPy forward (causal),
  parity với forward lattice hmmlearn (tol 1e-10), warmup 500 bars.

### M6 — Random Forest
- Labels: forward price move 12 bars vs 0.75·ATR (chỉ là target, purge/embargo).
- Features: HMM posterior/state/entropy/transition + delta + market features.
- Tuning trên validation slice, calibration chỉ khi cải thiện Brier.
- So sánh HMM-only / RF-only / HMM+RF ngoài mẫu.

### M7 — Regime Engine
- 8 operational regimes + permission (BUY_ONLY/SELL_ONLY/NO_TRADE — nghiên cứu).
- Thresholds/hysteresis/confirmation tối ưu trên validation, reason codes,
  confidence, expiry; state engine persist qua predictions.

### M8 — Backtest & Walk-forward
- Expanding window, purge/embargo, mỗi fold fit lại toàn bộ.
- Metrics: classification, false trend rate, detection delay, stability,
  trading simulation (PF, MaxDD, expectancy, win rate, avg R, missed trends).

### M9 — Registry & ONNX
- Model registry với status lifecycle + auto-approve gate (chỉ khi đạt
  F1 & false-trend-rate ngưỡng) — gate verified hoạt động.
- ONNX export cho RF + parity test (tol 1e-5, max diff đo được 8e-8).

### M10 — Dashboard (Next.js)
- 9 trang, Plotly charts, auth, DEMO banner cho synthetic_demo,
  Loading/Empty/Error/stale states.

### M11/M12 — API & Deployment
- API v1 đầy đủ; health; system status; stats.
- docker-compose (postgres/backend/worker/frontend/nginx), Dockerfiles,
  nginx rate-limit + mẫu TLS, worker standalone entry.

### Kiểm thử
- 83 pytest tests xanh (unit, leakage, parity, API, E2E training, collector logic).
- Smoke test API thật: seed 38.250 candles → train → approve → regime/latest
  → backtest 7 folds qua background worker.
