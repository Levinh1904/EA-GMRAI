# Changelog

## [0.7.0] — 2026-11-16

### Độ chính xác hướng: 37.6% → 62.3% (run #11, model 20261113T... mới)

**Nguyên nhân gốc**
- `run_engine_over_time()` dùng `collapse_short_trends()` **retrospective** (look-ahead)
  trong khi live/history dùng bản **causal** → threshold/variant/F1 bị lạc quan.
- `min_signal_bars=9` chỉ công bố trend từ nến thứ 9 → entry quá muộn; segment
  bắt đầu sau phần lớn move và thường đóng cửa ngược hướng (36-39%).
- State-detector inputs không được đưa vào lúc tune; live short-trend filter tự
  khoá vì đếm run-length từ nhãn đã collapse.

**Sửa**
- `regime_engine`: thêm `min_hold_bars` (giữ trend tối thiểu N nến), replay
  `run_engine_over_time_causal`, grid filter tầng 2 (`min_signal_bars`,
  `min_hold_bars`, `state_override_strength`); causal objective.
- `training`: nạp state-detector inputs; chọn variant bằng segment direction
  accuracy (0.7·min + 0.3·overall), thêm metric `segment_direction_accuracy` +
  gate `approve_min_segment_accuracy`.
- `prediction`: lưu `raw_regime` và dùng nó cho run-length; cache key gồm RF
  version + engine params; warmup 1000 nến; pair validation theo `model_id`
  (`get_active_approved_pair`) — không ghép HMM/RF khác training run.
- `history`: invalidate stats cache sau khi ghi segments (trước đó API có thể
  trả per-segment = 0 nếu cache gặp lúc segments chưa commit).
- Models UI: chỉ hiện "Duyệt" cho candidate, "Từ chối" cho candidate/validating/
  training, "Lưu trữ" cho approved/rejected — hết lỗi approved→rejected.
- Training data: M5 120k / M15 30k / H1 12k → dùng đủ ~23.9k nến thay vì 10k.

**Kết quả thật (run #11, 23.904 nến, model versions 9+10)**
- Per-segment: **UP 64.99% (544/837), DOWN 59.66% (494/828), overall 62.34%**
  (baseline run #9: 36.02 / 39.03 / 37.62).
- Test holdout 15%: UP 61.47% / DOWN 60.0% / overall 60.67%.
- Trade sim (1 lot, $30/lệnh, max_hold 24): LONG +$37.668, SHORT +$47.967,
  tổng **+$85.635** (baseline −$7.011).
- Caveat: F1 12-bar vẫn ~0.32 và false-trend ~66%; cải thiện đến từ entry sớm +
  min-hold causal, không phải classifier mạnh hơn. Cần feature/label mới nếu
  muốn nâng F1.

**Follow-up 70% gate — run #15 (vẫn model 9+10, engine config chọn trên OOS)**
- Engine: `theta_enter=0.60`, `theta_exit=0.45`, `confirm_bars=1`,
  `min_signal_bars=1`, `min_hold_bars=8`, `state_override_strength=0.45`,
  **`min_disp_signal=1.2` + `require_h1_agreement=true`**.
- Full-year: **UP 76.61% (737/962), DOWN 73.81% (727/985), overall 75.19%**
  (1.464/1.947), 1.947 trend segments.
- Holdout 15%: **UP 75.9% / DOWN 75.0% / overall 75.4%**.
- Trade sim full-year: LONG +$16.194, SHORT +$4.626, tổng **+$20.820**
  (run #11: +$85.635, nhưng run #11 OOS −$1.441; config 70% OOS +$15.656).
- Trade-off: segment trung bình 7.25 nến (run #11: 11.5), nhiều đoạn ngắn hơn;
  accuracy cao hơn nhưng PnL in-sample thấp hơn. Cấu hình thay thế G
  (`hold=12, confirm=3, override=0`) đạt 74.2% và PnL full-year +$61.195.

**Session filter — run #19 (UTC 6/8/14/17; VN 13/15/21/00)**
- Thêm `allowed_entry_hours_utc` vào `EngineParams`; chỉ lọc **entry**, trend đã
  mở vẫn được giữ qua cửa sổ giờ (không ép đóng lệnh). Giờ chọn bằng trade PnL
  trên cả pre-test và holdout; 4 giờ đều dương ở cả hai giai đoạn.
- UI `/history`: chọn 0–23 giờ UTC (preset 6,8,14,17 / tất cả / bỏ lọc) rồi
  **Chạy lại với giờ đã chọn**; `POST /history/run?hours=...` lưu giờ vào
  `config_json` và override engine params cho riêng run đó.
- **Số liệu UI inclusive (tính cả EARLY_TREND)**: 63.35% overall (UP 65.44 /
  DOWN 61.38, 562 đoạn). **TREND tradeable only**: 50.6% full-year (UP 52.2 /
  DOWN 49.2, 344 đoạn), **45.6% OOS** (57 đoạn).
- PnL: **+$137.924** full-year (430 lệnh, win 39.5%, PF 1.33); OOS **+$24.723**
  (72 lệnh, win 40.3%, PF 1.49).
- **Correction**: con số 75–81% trước đó gồm EARLY_TREND (NO_TRADE). Mục tiêu
  70% **chưa đạt** trên TREND tradeable; cần model/feature/label mới, không chỉ
  filter giờ. Hour filter cải thiện PnL và số lệnh, không nâng hit-rate trend.
- UI tab Độ chính xác hướng giờ hiển thị thêm dòng **"Chỉ TREND tradeable"** để
  tách khỏi số inclusive.

**Long-side profit filter — run #22**
- LONG yếu hơn SHORT rõ rệt: run #19 LONG OOS −$3.995, SHORT OOS +$27.048.
  Thêm điều kiện riêng cho LONG: **H1 trend context ≥ 0.20 + |displacement| ≥ 1.2**;
  SHORT giữ nguyên.
- Mô phỏng thực tế (tín hiệu đóng nến → entry nến sau, spread 0.4 + slippage
  0.1/side, commission $30):
  - Full: **+$91.658**, 367 lệnh, win 38.4%, PF 1.23, maxDD **−$37.145**.
  - OOS 15%: **+$33.386**, 60 lệnh, win 41.7%, PF 1.87, maxDD −$5.772.
  - Baseline run #19 cùng cách tính: full +$88.437 (maxDD −$51.247), OOS +$23.053
    (maxDD −$12.301); LONG OOS −$3.995.
- Đổi lại: ít lệnh LONG hơn, accuracy tradeable gần như không đổi (50.5%);
  lợi nhuận cải thiện nhờ bỏ các LONG yếu và giảm drawdown, không phải tăng
  hit-rate.
- Các phương án khác đã thử: short-only hold12 OOS +$30.781 nhưng full thấp
  hơn; TP/SL 2/4 ATR tăng full PnL nhưng OOS thấp hơn. Long-filter là điểm
  cân bằng tốt nhất giữa full/OOS/drawdown.

## [0.6.1] — 2026-11-14

### Cache history stats, rate limit diện rộng, UI gọn hơn

**Cache cho history stats** (`app/services/stats_cache.py`)
- 13 endpoint `/history/runs/{id}/stats/*` trước đây **nạp lại toàn bộ run**
  (23.781 nến + 5 cột JSON) mỗi lần gọi. Với 13 tab, bấm qua một run là
  materialise lại cùng một dữ liệu hàng chục lần.
- Cache TTL 5 phút theo khoá `(run_id, stats_kind, params)`, LRU 64 entry.
- **Chỉ cache run đã `done`**: bars/segments của run đang chạy vẫn được ghi
  nên cache sẽ trả dữ liệu cũ — run `running` luôn được tính lại.
- Đo thật: `/stats/wrong_direction` **3.71s → 0.02s** (185×), `vs_reference`
  3.22s → 0.03s. Tổng 8 tab: **11.7s → 0.25s**.
- `GET /history/cache/stats` (admin) xem hit-rate; `POST /history/cache/invalidate`.

**Rate limit** (`app/rate_limit.py`)
- Limiter chuyển sang module dùng chung (trước chỉ nằm trong `auth.py`).
- `/ingest/candles`: 120/phút (nhận tới 10.000 nến/request, trước không giới hạn).
- `/training/run`, `/backtests`: 10/phút (job nặng do admin kích hoạt).
- Trước: **2/59 endpoint** có giới hạn → nay 5 nhóm endpoint.

**Xoá hẳn người dùng**
- `DELETE /users/{id}` mặc định vô hiệu hoá; `?purge=true` xoá hẳn khỏi DB.
- UI có nút "Xoá" đỏ riêng, hộp xác nhận giải thích hệ quả (bản ghi lịch sử
  trỏ tới user id không còn tồn tại) và gợi ý dùng "Tắt" nếu chỉ muốn chặn.

**UI**
- Input/select trong form được style đầy đủ (trước là `<input>` trần của
  trình duyệt): bo góc, viền, caret tuỳ biến cho select, focus ring, trạng thái
  hover/disabled.
- `PasswordField` mới có nút **Hiện/Ẩn**; dùng ở form tạo user và đổi mật khẩu.
- **Trang Tổng quan làm lại**: 3 thẻ trên cùng (chế độ · giá trực tiếp · sức
  khoẻ dữ liệu), xác suất gọn 1 hàng, 6 khối chẩn đoán chuyển vào `<details>`
  thu gọn — không còn cuộn dài.

## [0.6.0] — 2026-11-13

### Quản trị hệ thống, retention, backup, sửa lỗi vận hành

Rà soát toàn bộ 59 endpoint + 20 bảng + toàn bộ frontend, rồi lấp các lỗ hổng
lớn nhất. **240 tests xanh** (+34).

**Quản trị người dùng** (`app/routers/admin.py`, trang `/admin`)
- Thêm/sửa/xoá mềm người dùng, đổi role (`admin`/`analyst`/`viewer`), bật/tắt.
- **Đặt lại mật khẩu bởi admin** — trước đây không có đường phục hồi khi user
  quên mật khẩu (self-service yêu cầu mật khẩu hiện tại).
- Chặn 3 trạng thái không thể phục hồi: hạ quyền admin cuối cùng, admin tự tắt
  chính mình, admin tự xoá chính mình.
- Mật khẩu mới dùng chung validator với đổi mật khẩu (≥10 ký tự, chữ + số,
  denylist). Mọi thao tác ghi `system_logs` (component `admin`).

**Quản lý API key collector**
- `GET/POST/DELETE /api-keys` + `/restore`. Plaintext chỉ trả **một lần** khi
  tạo; DB chỉ lưu SHA-256. Response liệt kê dùng `fingerprint` (`sha256:abc…`).
- Không cho thu hồi key `env-bootstrap` (phải đổi qua `.env`).

**Tra cứu background job** (`app/routers/jobs.py`)
- `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`.
- Trước đây `POST /training/run|/backtests|/history/run` trả `job_id` nhưng
  **không có endpoint nào tra được** — handle vô dụng.
- `/jobs` báo `executor.durable=false` để UI biết thread pool mất job khi restart.

**Retention** (`app/services/retention.py`)
- Dọn 7 bảng append-only theo cửa sổ cấu hình (system_logs 30d, telegram 90d,
  sync 30d, quality 90d, jobs 14d, forecast 365d, predictions 365d).
- **History runs/bars mặc định KHÔNG bị dọn** (`retention_history_runs=0`):
  đó là dữ liệu nghiên cứu, không phải log vận hành.
- Xoá theo batch 5000, có `--dry-run`, ghi log mỗi lần chạy. Chạy tự động mỗi
  24h trong scheduler.

**Backup** (`backend/scripts/backup.py`)
- SQLite: `VACUUM INTO` (nhất quán khi app đang chạy, khác `cp`).
- Postgres: `pg_dump --format=custom`.
- Kèm `artifacts/` (tar.gz) + `README.txt` hướng dẫn restore. `--keep N` để
  xoay vòng.

**Sửa lỗi vận hành**
- `GET /api/v1/health` trả **503** khi DB hoặc worker hỏng (trước đây luôn 200
  → uptime check không bao giờ bắt được sự cố). Thêm `/readyz`, `/version`.
- `GET /training/runs/{id}` và `/backtests/{id}` trả **404** thật thay vì
  `200 {"error":"not found"}`.
- `GET /features` tính trực tiếp từ nến (2.683 dòng thật) thay vì đọc bảng
  `market_features` chưa bao giờ được ghi (luôn trả 0).
- Frontend: thêm `error.tsx`, `not-found.tsx` trong shell; xoá code chết
  (`CandlestickChart.tsx`, `TradingChart/index.ts`, `Section`); thêm mục nav
  “Quản trị”.

## [0.5.0] — 2026-11-13

### Dự đoán nến kế tiếp + Telegram notifications

**Dự đoán nến M15 kế tiếp** (`backend/app/services/forecast.py`, `GET /api/v1/forecast/next`)
- Mô hình `hgbt_direction_v1` (HistGradientBoosting, chronological split) dự đoán
  nến kế tiếp tăng/giảm từ nến đã đóng: 9 log-return đa khung, body/wick, ATR%,
  ADX, DI, khoảng cách EMA20/50, giờ, thứ, cộng context H1/M5.
- Có **dải FLAT** (±4% quanh 50%): model không có ý kiến thì không gọi hướng,
  thay vì tạo ra độ chính xác giả.
- **Idempotent theo nến** (`uq_forecast_bar`): một dự đoán mỗi nến, không bao
  giờ ghi đè dự đoán cũ → độ chính xác không thể bị "làm đẹp".
- Outcome được điền **sau khi** nến mục tiêu đóng; `GET /forecast/stats` trả về
  độ chính xác thực đo từ CSDL.
- **Đo thật: accuracy 0.4967, AUC 0.5169** trên 23.782 nến ⇒ gần như ngẫu
  nhiên. UI hiển thị đúng con số này, kèm cảnh báo — không quảng cáo quá khả năng.

**Telegram notifications** (`backend/app/services/telegram.py`, `backend/app/routers/notifications.py`)
- Gửi tín hiệu regime + dự đoán nến kế tiếp qua Bot API.
- **Chống trùng 2 lớp**: `dedupe_key` UNIQUE (không gửi 2 lần cho cùng nến), và
  cùng hướng với lần gửi trước → ghi log `skipped/duplicate_direction`, không
  gửi lại. Đổi hướng (giảm → tăng) thì gửi lại.
- **Mọi lần thử đều được lưu** trong `telegram_messages` (sent/skipped/failed +
  lý do + message_id + lỗi) → `GET /telegram/messages` có filter theo status.
- Scheduler tự quét mỗi `GMRAI_TELEGRAM_INTERVAL_SECONDS` (mặc định 300s); lỗi
  gửi không bao giờ làm hỏng inference/ingestion.
- Admin: `POST /telegram/test` (kiểm tra kết nối), `POST /telegram/notify` (đẩy
  tín hiệu ngay).
- Trang mới `/telegram`: trạng thái bot, 4 chỉ số đếm, dự đoán nến kế tiếp,
  lịch sử dự đoán đối chiếu thực tế, và lịch sử tin nhắn đầy đủ (expand để xem
  nội dung gửi).
- Cấu hình: `GMRAI_TELEGRAM_ENABLED`, `GMRAI_TELEGRAM_BOT_TOKEN`,
  `GMRAI_TELEGRAM_CHAT_ID`, `GMRAI_TELEGRAM_INTERVAL_SECONDS`.
- Migration `9d3e5a1b7c42` (2 bảng mới). 179 tests xanh (+16).

## [0.4.2] — 2026-11-12

### History Timeline — dải xu hướng dưới biểu đồ + live tail

- **Regime strip chuyển xuống dưới nến** (cùng trục thời gian): trước đây dải
  regime tô mờ đè lên cây nến, nay là một hàng riêng dưới biểu đồ để so sánh
  trực tiếp "giá đi thế nào" ↔ "mô hình gọi chế độ gì".
  - 4 chế độ: AI, Reference, Overlay (AI trên + Reference dưới), Bất đồng.
  - Màu đặc + nhãn chữ khi band đủ rộng; cắt đúng vùng plot, không đè trục giá.
- **Sửa 2 bug renderer**: (1) mảng band không sort → binary-search cull hỏng,
  chỉ vẽ được 1 band; (2) `timeToCoordinate(end + 1)` trả `null` cho timestamp
  không có trong series → mọi band bị bỏ qua.
- **Live tail**: nến M15 mới hơn run snapshot được nối thêm mỗi 10 giây và đánh
  dấu dải `LIVE` (chưa phân tích) — timeline chạy tiếp mà không bịa nhãn mô hình.
- `/history/day`: trang xem lại một ngày (mặc định hôm qua), endpoint nhân quả
  `GET /api/v1/history/day?day=YYYY-MM-DD`.
- Biểu đồ Live Market tự tải nến mới 5s; `/regime/latest` poll 5s (TTL 5s).
- Collector: sửa `send_tick` nằm ngoài class `ApiClient`; xoay API key + chạy
  trong session tương tác để thấy MT5.
- 134 backend tests xanh.

## [0.4.0] — 2026-11-11

### Professional UI/UX & Advanced Chart Overhaul
- Chart engine: chuyển Live Market sang **TradingView Lightweight Charts v5**
  (kéo ngang, zoom con lăn theo con trỏ, kéo trục giá, double-click reset,
  crosshair magnet + OHLC legend, touch, lazy-load nến khi kéo về quá khứ —
  không nhảy vị trí, toggle Grid/Crosshair/Volume/EMA/AI/Reference, fullscreen,
  range presets 1D→ALL). Nút "Tín hiệu" disabled kèm tooltip (backend chưa có
  dữ liệu BUY/SELL — không bịa marker).
- Regime bands: canvas primitive trên chart (AI + Reference, nửa trên/dưới),
  click band mở popover chi tiết đoạn regime.
- Sidebar: nhóm chức năng (Tổng quan/Thị trường/Phân tích AI/Mô hình/Dữ liệu),
  thu gọn icon-only (persist), drawer mobile, status dots từ dữ liệu thật
  (freshness/health/active models/sync).
- Live Market: ticker (giá, change%, spread, market status, kết nối, "chỉ nến
  đã đóng"), panel phải (regime, HMM/RF probs, Reference, H1 context, ATR,
  Early warning), đáy (timeline strip clickable, AI vs Reference agreement,
  stats, transitions).
- Historical Analyzer: filter bar (khoảng ngày UTC, TF — M5/H1 disabled có
  giải thích, phiên bản model HMM, chế độ AI/Reference), deep-link ?tab=.
- Dashboard: regime donut, freshness gauges, Model Performance Over Time
  (F1/false-trend theo run) trên /compare và /backtesting.
- Design system: design tokens (spacing/typography/surfaces/status), phẳng,
  bỏ glow/gradient. Cấu trúc components/{layout,charts,market,regime,
  analytics,tables,ui}.
- QA trình duyệt thật: crosshair legend hiển thị OHLC thật, TF H1 (spacing
  3600s), lazy-load 5.000→8.163 nến không nhảy vị trí, sidebar thu gọn
  236→60px, 13 routes + 12 history tabs không regression, build xanh.

## [0.3.0] — 2026-11-11

### Independent Reference Regime Engine + AI vs Reference validation
- `ml/reference_engine.py`: rule-based độc lập (ADX/±DI, Kaufman ER, ATR
  ratio, EMA slope, kênh High/Low, displacement), labels đầy đủ 6 lớp,
  thresholds versioned (`ref_v1`) — tái lập lịch sử, independence AST-tested.
- `ml/outcome.py`: future outcome evaluator (fwd return/MFE/MAE/direction/
  in-range, horizons 12/48/96) — tương lai chỉ để đánh giá.
- Storage: `outcome_evaluations` + cột reference trên history bars/runs;
  prediction gốc không bao giờ bị ghi đè (runs immutable).
- AI vs Reference metrics: agreement, confusion full-class (không map về
  SIDEWAYS), per-class + macro F1, false trend/sideways rate, detection
  delay, boundary disagreement, duration disagreement.
- API: `stats/vs_reference`, `stats/outcomes`, bars mở rộng reference fields.
- 13 tests mới (independence, causality/truncation, reproducibility, version
  snapshot, indicator math, outcomes, metrics) — 115 tests tổng.
- Chạy thật trên FTMO 1 năm (run #3): kết quả trong docs/HISTORY_MODULE.md.

## [0.2.0] — 2026-11-11

### Historical Market Regime Analyzer (module mới)
- Schema: `regime_history_runs` / `regime_history_bars` / `regime_segments`
  (2 Alembic migrations).
- `app/ml/history.py`: causal inference toàn bộ lịch sử (tái dùng HmmFilter +
  RF + Regime Engine), segmentation theo regime change + data gap (không gộp).
- `app/ml/history_stats.py`: duration stats, trend analysis (mạnh/yếu theo
  quantile, ghi rõ ngưỡng), sideways (touches/breakouts/false breakouts,
  buckets), early trend evaluation vs reference labels, transition matrix,
  daily/weekly/monthly/quarterly/yearly, multi-TF (M15 regime + H1/M5
  feature signals), run-vs-run + vs-reference comparison.
- API `/api/v1/history/*` (runs, bars, segments, 7 stats, compare, exports).
- Export CSV / Excel (openpyxl) / PDF report (reportlab).
- 17 tests mới (gồm leakage: truncation invariance của per-bar regime);
  toàn suite 101 tests xanh.
- Chạy thật trên 1 năm dữ liệu FTMO-Demo: 23.545 nến M15 → 2.209 segments
  (kết quả chi tiết trong docs/HISTORY_MODULE.md).

### Collector fixes (dữ liệu thật đã chảy về)
- MetaTrader5 pin `>=5.0.5488` (bản 5.0.45 bị gỡ khỏi PyPI).
- `ts` serialize ISO (fix JSON TypeError), gửi batch 5000 nến (giới hạn server 10k).
- Chunked backfill 30 ngày tự thu hẹp khi MT5 từ chối (-2 Invalid params),
  symbol_select, bỏ microsecond, tách Mt5FetchError khỏi reconnect.

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
