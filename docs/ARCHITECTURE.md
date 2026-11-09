# GMRAI — Kiến trúc hệ thống

## 1. Sơ đồ tổng thể

```
FTMO MT5 (Windows)
   └── Data Collector (Python, MetaTrader5 lib)
         │  nến đã đóng M5/M15/H1 (HTTPS + X-API-Key)
         ▼
Ingestion API (FastAPI) ──► PostgreSQL
         │                      │
         │                      ▼
         │              Data Processing Pipeline (quality checks, gap/dup)
         │                      │
         │                      ▼
         │              Feature Engineering (M15 + H1 + M5, versioned)
         │                      │
         │              ┌───────┴────────┐
         │              ▼                ▼
         │        Gaussian HMM      Random Forest
         │        (5 states)        (3-class regime)
         │              └───────┬────────┘
         │                      ▼
         │              Regime Engine (thresholds, hysteresis, confidence)
         │                      │
         │                      ▼
         │              Model Registry + ONNX Export
         │                      │
         ▼                      ▼
Backtest Engine ◄────── Walk-forward Validation (purge/embargo)
         │
         ▼
FastAPI /api/v1 ──► Next.js Dashboard
         └──────────► EA (tương lai, chỉ truy xuất kết quả phân tích)
```

## 2. Thành phần

### 2.1 Data Collector (`collector/`)
- Chạy trên Windows PC/VPS có MT5 Terminal đã đăng nhập FTMO.
- Đọc lịch sử nến XAUUSD M5/M15/H1 qua MetaTrader5 Python API.
- Chỉ gửi nến đã đóng; chu kỳ đồng bộ định kỳ; resync N nến gần nhất để xử lý cập nhật muộn.
- Checkpoint JSON để tiếp tục sau restart; tự phục hồi khi MT5 mất kết nối (retry + backoff).
- Backfill: `--backfill DAYS`. Log rotate. Không tự tạo dữ liệu giả.
- Gửi lên cloud qua HTTPS (Ingestion API) với `X-API-Key`.

### 2.2 Ingestion API
- `POST /api/v1/ingest/candles`: batch nến, upsert theo unique `(symbol, timeframe, ts)`.
- Từ chối nến đang hình thành; validate OHLC hợp lệ; ghi `data_sync_logs`.

### 2.3 PostgreSQL
- Lưu OHLC, features, predictions, model metadata, backtest results, logs.
- Index `(symbol, timeframe, ts)`, unique constraint candle key, UTC timestamps, pagination.
- Chi tiết: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md).

### 2.4 Data Processing Pipeline
- Quality checks định kỳ: gap detection (theo timeframe), duplicate, candle lỗi (O/H/L/C bất biến, high<low...), stale data.
- Ghi `data_quality_reports`; dashboard Data Center hiển thị.

### 2.5 Feature Engineering
- M15 features: `ret1`, `ret4`, `atr_ratio`, `ema_slope`, `efficiency_ratio`, `adx_norm`, `di_gap`.
- H1 context: EMA slope, ATR regime, ADX, trend context (nối vào từng thanh M15 tại thời điểm đóng).
- M5 timing: short-term returns, volatility, momentum.
- Chỉ dùng nến đã đóng; scaler fit trên TRAIN; NaN/Inf xử lý; feature version hóa.
- Chi tiết: [DATA_PIPELINE.md](DATA_PIPELINE.md).

### 2.6 AI Training Engine
- HMM: hmmlearn GaussianHMM, 5 states, diag covariance, multistart; lưu model + state mapping.
- RF: scikit-learn RandomForestClassifier 3 lớp (TREND_UP/TREND_DOWN/SIDEWAYS), target từ lợi nhuận tương lai (label leakage kiểm soát bằng purge/embargo).
- Training chạy trong Background Worker, trạng thái lưu `training_runs`.
- Chi tiết: [AI_MODEL_DESIGN.md](AI_MODEL_DESIGN.md).

### 2.7 Operational Regime Engine
- Tổng hợp HMM posterior + RF probabilities → regime vận hành: SIDEWAYS, TREND_UP, TREND_DOWN, EARLY_TREND_UP/DOWN, TRANSITION, HIGH_VOLATILITY, UNKNOWN.
- Probability thresholds + hysteresis + confirmation bars + confidence + reason codes + expiry.
- Ngưỡng được tối ưu trên validation, kiểm tra trên test độc lập (không chọn ngưỡng cảm tính).

### 2.8 Backtest Engine
- Chronological split; walk-forward (expanding/rolling); purge/embargo; out-of-sample.
- Metrics: classification (precision/recall/F1, confusion, false trend rate, detection delay, regime duration, state stability) + trading simulation (profit factor, max DD, expectancy, win rate, average R, opportunities, missed trends) — simulation chỉ là công cụ nghiên cứu.

### 2.9 Model Registry
- Mỗi model: ID, version, training timestamp, dataset range, feature version, hyperparameters, validation/test metrics, artifact path, status (Training → Validating → Candidate → Approved/Rejected → Archived).
- Không tự động Approved nếu chưa đạt điều kiện kiểm định.

### 2.10 FastAPI
- Versioned `/api/v1`: auth, ingestion, market, features, quality, training, backtest, registry, regime, prediction, onnx, stats, system.
- JWT auth + role; rate limiting; pagination; health check.

### 2.11 Dashboard (Next.js)
- Trang: Overview, Live Market, AI Regime, Training Center, Backtesting, Model Comparison, Model Registry, Data Center, Settings.
- Trạng thái Loading/Empty/Error/stale rõ ràng; dữ liệu demo được gắn nhãn rõ.

### 2.12 Background Worker
- In-process ThreadPoolExecutor trong backend (startup qua lifespan) cho: quality checks định kỳ, retrain định kỳ, backtest job.
- Bảng `background_jobs` lưu trạng thái; automation bật/tắt qua `GMRAI_AUTOMATION_ENABLED`.
- Production có thể thay bằng Celery/Redis mà không đổi interface (documented upgrade path).

## 3. Quyết định kiến trúc quan trọng

| # | Quyết định | Lý do |
|---|---|---|
| A1 | Regime chính = M15; H1 = context; M5 = timing | Theo cấu hình đã chốt |
| A2 | HMM inference = filtered posterior (forward only) | Không lookahead; Viterbi/smoothing toàn chuỗi bị cấm cho tín hiệu lịch sử |
| A3 | Canonical HMM inference = NumPy `HmmFilter` tự viết | Parity với hmmlearn; là bản tham chiếu cho port MQL5/ONNX sau này |
| A4 | RF không nhân xác suất độc lập với HMM | RF nhận HMM posterior làm feature; chọn ensemble chỉ khi OOS tốt hơn |
| A5 | SQLite cho dev/test, PostgreSQL cho prod (SQLAlchemy chung) | Docker không có trên máy dev; schema/migration dùng chung |
| A6 | Background job in-process | Giảm dependency vận hành giai đoạn đầu; upgrade path Celery |
| A7 | Ingestion dùng static API key (hash trong DB) | Collector không cần interactive login |
| A8 | Seed demo = dữ liệu tổng hợp gắn nhãn `source=synthetic_demo` | Có thể chạy end-to-end không cần MT5; không bao giờ hiển thị như live |

## 4. Cấu hình môi trường (single source of truth)

- Backend: `backend/.env` (template `backend/.env.example`) — prefix `GMRAI_`.
- Collector: `collector/.env` (template `collector/.env.example`) — MT5 credentials chỉ nhập trên máy chạy Collector.
- Frontend: `NEXT_PUBLIC_API_URL`.
- Không commit secret vào Git (`.env` trong `.gitignore`).
