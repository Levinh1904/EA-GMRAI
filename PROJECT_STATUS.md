# GMRAI — Project Status

> Cập nhật: 2026-11-16 — **v0.7.0: direction accuracy 37.6% → 62.3% (run #11).**

## 0. v0.7.0 — Độ chính xác hướng (model 9+10, run #11)

- **Root cause**: training/eval dùng retrospective collapse (look-ahead) trong
  khi live/history dùng causal; `min_signal_bars=9` làm entry muộn; state
  detector không được tune cùng; live short-trend filter tự khoá.
- **Fix**: `min_hold_bars` + causal replay; chọn variant theo segment accuracy;
  nạp state inputs khi tune; lưu `raw_regime`; pair validation theo `model_id`;
  M5/M15/H1 limits đủ 1 năm; invalidate stats cache sau commit segments.
- **Kết quả thật**: run #11 (23.904 nến, model versions 9+10) — UP **64.99%**
  (544/837), DOWN **59.66%** (494/828), overall **62.34%** (1.038/1.665).
  Baseline run #9: 36.02 / 39.03 / 37.62.
- **Holdout 15%**: UP 61.47 / DOWN 60.0 / overall 60.67. Trade sim: LONG
  +$37.668, SHORT +$47.967, tổng **+$85.635** (baseline −$7.011).
- **Caveat**: F1 12-bar ~0.32, false-trend ~66% — path metric cải thiện nhờ
  entry sớm/min-hold causal, không phải classifier tốt hơn. Bước tiếp theo nếu
  cần: feature/label mới + walk-forward selection.
- **70% gate (run #15)**: thêm `min_disp_signal=1.2` + H1 agreement vào entry
  gate — full-year **UP 76.61% / DOWN 73.81% / overall 75.19%**; holdout 15%
  **75.4%**; PnL full-year +$20.820, OOS +$15.656 (run #11 OOS −$1.441).
  Segment trung bình 7.25 nến; cấu hình G thay thế (hold=12, confirm=3,
  override=0) đạt 74.2% và PnL full-year +$61.195.
- **Session filter (run #19)**: chỉ entry trong **UTC 6/8/14/17** (VN
  13/15/21/00); UI History chọn giờ và chạy lại được. UI inclusive (EARLY
  counted) 63.35% (UP 65.44/DOWN 61.38, 562 đoạn); **TREND tradeable only
  50.6%** (UP 52.2/DOWN 49.2, 344 đoạn), **OOS 45.6%** (57 đoạn). PnL
  **+$137.924** (430 lệnh, win 39.5%, PF 1.33); OOS **+$24.723**.
- **Correction**: 75–81% trước đó gồm EARLY_TREND (NO_TRADE). Mục tiêu 70%
  **chưa đạt** trên TREND tradeable; cần model/feature/label mới. UI giờ hiện
  thêm dòng "Chỉ TREND tradeable" để tránh hiểu nhầm.
- **Long-side profit filter (run #22)**: LONG cần H1 ≥ 0.20 + |displacement| ≥
  1.2; SHORT giữ nguyên. Mô phỏng thực tế (entry nến sau, spread/slippage):
  full **+$91.658** (maxDD −$37.145), OOS **+$33.386** (maxDD −$5.772), LONG
  OOS +$8.110 (baseline −$3.995). Accuracy tradeable 50.5% — lợi nhuận tăng
  nhờ bỏ LONG yếu, không phải tăng hit-rate.
- Models 9/10 approved; 5/6 archived; 7/8 candidate.

## 0. v0.4.1 — Live data & day history

- **Collector live hoạt động lại**: API key đã xoay (rotate) được đồng bộ sang máy
  Windows; collector chạy trong session tương tác (scheduled task `/it`) để thấy
  MT5 — sync nến mỗi 60s, tick Bid/Ask mỗi 1s.
- **Sửa lỗi `send_tick` không nằm trong class** `ApiClient` (collector gọi được).
- **Trang `/history/day`**: xem lại một ngày (mặc định hôm qua) — OHLC, dải chế
  độ, phân bố AI vs Reference, segments, chi tiết từng nến. Endpoint
  `GET /api/v1/history/day?day=YYYY-MM-DD` **nhân quả**: chỉ dùng nến trước cuối
  ngày được chọn.
- **Regime & biểu đồ cập nhật liên tục**: chart tải lại nến mới mỗi 5s; regime
  poll 5s với TTL cache 5s (DB vẫn đảm bảo 1 dòng/nến).
- 134 tests xanh.

## 0. v0.4.2 — Timeline: dải xu hướng dưới biểu đồ + cập nhật liên tục

- **Dải xu hướng (regime strip) chuyển xuống dưới biểu đồ nến**, cùng trục thời
  gian, để so sánh trực tiếp với giá. Trước đây dải tô mờ đè lên nến.
  - 4 chế độ: AI / Reference / Overlay (AI trên + Reference dưới) / Bất đồng.
  - Màu đặc, tự vẽ nhãn ("Đi ngang", "Xu hướng giảm"…) khi band đủ rộng.
  - Cắt đúng vùng plot — không đè lên trục giá.
  - Sửa 2 bug renderer: mảng band chưa sort (binary search hỏng → chỉ vẽ 1 band)
    và `timeToCoordinate(end + 1)` trả null (skip mọi band).
- **Timeline cập nhật liên tục**: nến M15 mới hơn run snapshot tự nối vào mỗi
  10s, đánh dấu dải LIVE "chưa phân tích" (không bịa nhãn mô hình).
- 134 tests xanh.

## 1. Trạng thái milestones

| Milestone | Trạng thái |
|---|---|
| M1 Architecture & skeleton | ✅ |
| M2 FTMO Data Collector | ✅ code + unit tests; ⚠️ MT5 integration cần Windows+FTMO |
| M3 Backend & Database | ✅ |
| M4 Feature Engineering | ✅ |
| M5 HMM Regime Detection | ✅ (khóa bẫy `predict_proba` smoothed) |
| M6 Random Forest | ✅ |
| M7 Regime Engine | ✅ |
| M8 Backtest & Walk-forward | ✅ |
| M9 Model Registry & ONNX | ✅ |
| M10 Dashboard (Next.js, 9 trang) | ✅ build xanh + QA trình duyệt thật |
| M11 API & Security | ✅ |
| M12 Deployment preparation | ✅ (compose/Dockerfiles/nginx; chưa chạy do máy dev không có Docker) |
| M13 Docs & audit | ✅ |

## 2. Kết quả đã chạy thật (không mô phỏng)

- **82 pytest tests xanh** (unit, leakage, HMM parity 1e-10, ONNX parity ≤1e-5
  đo được 8e-8, API, E2E training, collector logic).
- Seed demo 38.250 candles (`synthetic_demo`, nhãn rõ), quality checks 0 gap.
- Training thật trên DB dev: chọn variant `combined`; test F1 0.3244 →
  **gate từ chối auto-approve đúng** (ngưỡng 0.55); approve thủ công qua API.
- Regime live qua API: SIDEWAYS 68.7%, NO_TRADE, reason codes đầy đủ.
- Backtest walk-forward qua background worker: 7 folds, combined F1 0.3491±0.073.
- Migration alembic up → down → up OK.
- Frontend: `npm run build` xanh; QA bằng trình duyệt thật (login → Overview,
  Market với 2 biểu đồ Plotly render, AI Regime với posterior/engine params/
  state mapping) — banner DEMO + cảnh báo stale hoạt động đúng.

## 2.5. Module Historical Market Regime Analyzer — HOÀN THÀNH (v0.2.0)

- Backend: schema (3 bảng + 2 migrations), engine causal (truncation-invariance
  test chống lookahead), 7 nhóm thống kê, compare, export CSV/XLSX/PDF,
  API `/api/v1/history/*` — 102 tests xanh toàn suite.
- Frontend: trang `/history` 10 tabs (Timeline zoomable + regime strip,
  Trends, Sideways, Early Trend, Segments, Transition Matrix, Multi-TF,
  Compare, Reports) — build xanh, QA trình duyệt thật + 36 check tự động.
- Đã chạy trên **dữ liệu FTMO-Demo thật 1 năm** (run #1: 23.545 nến M15,
  2.209 segments; SIDEWAYS 80.2%; Early Trend ~69.5% thành công, delay ~3.7
  nến M15; 80 breakouts/7 false). Chi tiết: docs/HISTORY_MODULE.md.
- 2 bug backend do QA phát hiện đã sửa + regression tests (periods M/Q/Y,
  xlsx bars tz-naive).
- Dữ liệu thật từ collector đang chảy về liên tục (99.656 nến ftmo_mt5).

## 2.6. Independent Reference Engine & AI vs Reference (v0.3)

- `ml/reference_engine.py` (ref_v1): rule-based độc lập, versioned, AST-tested
  độc lập cấu trúc với HMM/RF/Operational Engine; tái lập lịch sử theo config.
- `ml/outcome.py`: đánh giá tương lai 12/48/96 nến (fwd return/MFE/MAE/
  direction/in-range) — không đổi prediction gốc (test khóa).
- Lưu song song trên từng nến: AI label (immutable) + reference label +
  triggered rule + indicators + versions; bảng `outcome_evaluations`.
- AI vs Reference: agreement, confusion full-class, per-class+macro F1, false
  trend/sideways rate, detection delay, boundary & duration disagreement.
- Frontend: Timeline 4 chế độ dải (AI/Reference/Overlay/Bất đồng), panel
  "Chi tiết thanh nến" (OHLC + AI probs + reference indicators + rule),
  tab "So sánh Reference" + "Kết quả tương lai" (12 tabs tổng).
- Kết quả thật (run #3, 1 năm FTMO-Demo): agreement 17.9%; F1 TREND_UP
  0.548 / TREND_DOWN 0.520; false trend 21.8% / false sideways 20.8%;
  boundaries 960/1958 matched (mean 1.04 nến); outcomes 12 nến: trend win
  ~45-46% — model hiện tại chưa có edge trên tài khoản demo (báo cáo trung thực).
- 115 tests xanh (13 test mới: independence, causality, reproducibility,
  indicator math, outcomes, metrics).

## 2.7. UI/UX Professional Overhaul (v0.4.0)

- Live Market dùng lightweight-charts v5 (TradingView-like): pan/zoom/
  crosshair/lazy-load verified trong trình duyệt thật (xem CHANGELOG 0.4.0).
- Sidebar nhóm + thu gọn + status dots; History có filter bar (ngày, model
  version, chế độ AI/Reference); dashboard thêm donut/gauges/model performance.
- 13 routes + 12 history tabs không regression; build xanh; backend không đổi.

## 3. Blocker còn lại (cần người dùng)

| Blocker | Cần gì |
|---|---|
| MT5 collector integration test | máy Windows + MT5 + tài khoản FTMO (xem collector/README.md) |
| PostgreSQL/docker compose chạy thật | máy có Docker (hoặc server) |
| Production deploy | server/domain + phê duyệt triển khai |
| Dữ liệu XAUUSD thật | chạy collector với tài khoản FTMO |

## 4. Cấu trúc bàn giao

```
GMRAI/
├── backend/     FastAPI + ML (HMM/RF/regime/backtest/ONNX) + Alembic + 82 tests
├── collector/   FTMO MT5 Data Collector (Windows)
├── frontend/    Next.js dashboard (9 trang)
├── docs/        10 tài liệu (thiết kế + API_CONTRACT)
├── scripts/     seed_demo_data.py
├── docker/      Dockerfiles + nginx.conf
├── docker-compose.yml
├── README.md / INSTALLATION_GUIDE.md / OPERATIONS_GUIDE.md /
│   TROUBLESHOOTING.md / CHANGELOG.md / PROJECT_STATUS.md
```

## 5. Bước tiếp theo cho người dùng

1. Chạy collector trên Windows có MT5 + FTMO (dữ liệu thật).
2. Deploy lên server (docker compose) khi có server/domain.
3. Theo dõi Training Center/Backtesting; approve model đạt gate; EA có thể
   đọc `GET /api/v1/regime/latest` (nghiên cứu, không gửi lệnh).
