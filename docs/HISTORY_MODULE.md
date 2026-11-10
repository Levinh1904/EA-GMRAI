# GMRAI — Historical Market Regime Analyzer (thiết kế module)

## 1. Mục đích

Phân tích toàn bộ lịch sử regime của XAUUSD (M15 làm khung chính): khi nào
Trend Up/Down, Sideways, Early Trend, Transition, High Volatility; mỗi trạng
thái kéo dài bao lâu; xu hướng mạnh/yếu theo chỉ số định lượng; AI phát hiện
xu hướng sớm hay muộn; so sánh các phiên bản model.

**Không giao dịch, không đặt lệnh. Reference labels chỉ dùng để đánh giá.**

## 2. Nguyên tắc dữ liệu (bắt buộc)

- Nguồn: nến đã lưu trong DB. **Không trộn nguồn** — run chọn `ftmo_mt5`
  nếu tồn tại; nếu chỉ có dữ liệu demo thì dùng `synthetic_demo` và ghi rõ
  trong run + giao diện.
- Chỉ phân loại nến đã đóng. Không chế dữ liệu thiếu — lỗ hổng dữ liệu làm
  **tách segment** (`split_reason=data_gap`), không bao giờ gộp để mất thông tin.
- Timestamp UTC xuyên suốt.

## 3. Causal inference (chống lookahead)

- Per-bar regime = pipeline runtime hiện có: `HmmFilter` (forward filtered
  posterior, KHÔNG smoothing) → RF → Operational Regime Engine (hysteresis
  tuần tự theo thời gian).
- Test khóa: regime tại t bất biến khi thêm dữ liệu tương lai
  (`test_inference_is_causal_truncation_invariance`).
- Early Trend là tín hiệu causal tại thời điểm t; dữ liệu tương lai (labels
  từ realized forward returns) chỉ được dùng ĐỂ ĐÁNH GIÁ tín hiệu sau đó.

## 4. Cấu trúc dữ liệu

- `regime_history_runs`: 1 lần phân tích (model versions, source, khoảng dữ liệu).
- `regime_history_bars`: per-bar regime + HMM/RF probs + OHLC + features
  (atr_ratio, adx_norm, efficiency_ratio, h1_trend_context, m5_momentum).
  Unique `(run_id, ts)`; index `(run_id, ts)`.
- `regime_segments`: các đợt regime liên tục với đầy đủ thống kê giá/ATR/
  ADX/efficiency/HMM probs/MFE/MAE/touches; index `(run_id, start_ts)`.

Thống kê tổng hợp tính **trên segments đã lưu** (không inference lại) —
mở dashboard nhanh với hàng trăm nghìn nến.

## 5. Các phép phân tích

| Phép | Phương pháp |
|---|---|
| Duration stats | occurrences, total/mean/median/longest/shortest, p25/p75/p90, occupancy, transitions |
| Trend mạnh/yếu | **Quantile** trên dân số segment: score = 0.5·efficiency + 0.5·adx_norm; strong ≥ p75, weak ≤ p25 (ghi rõ công thức + ngưỡng, cấu hình được) |
| Sideways | range width, touches (band 10% width), breakouts, false breakouts (breakout < 4 bars rồi quay lại SIDEWAYS — heuristic ghi rõ), buckets thời lượng cấu hình được |
| Early Trend | window đánh giá 12 bars mặc định; outcome vs reference labels: confirmed / wrong_direction / no_trend; success rate + detection delay |
| Transition matrix | tần suất chuyển regime vận hành thực tế (phân biệt rõ với transition xác suất nội tại của HMM) |
| Daily/weekly/... | mỗi bar đóng góp đúng vào bucket chu kỳ của nó (xử lý segment qua nửa đêm) |
| Multi-TF | M15 regime + **tín hiệu feature thật**: H1 context (h1_trend_context ±0.15), M5 timing (m5_momentum ±0.5) — KHÔNG tự chế regime cho M5/H1 |
| Model comparison | run-vs-run (agreement, confusion, durations) + vs reference labels (precision/recall/F1, false trend rate, detection delay) |

## 6. API & UI

- API: `GET/POST /api/v1/history/*` (xem API_CONTRACT.md).
- UI: trang `/history` với 10 tabs (Tổng quan, Timeline, Trend, Sideways,
  Early Trend, Segments, Transition Matrix, Multi-TF, So sánh, Export).
- Export: CSV / Excel (openpyxl) / PDF (reportlab).

## 7. Kết quả chạy thật (run #1, dữ liệu FTMO-Demo 1 năm)

- 23.545 nến M15 (2025-11-11 → 2026-11-10 UTC), 2.209 segments.
- SIDEWAYS 80.2% thời gian (mean 4h27m); TREND_UP 150 đợt (mean 3h11m);
  TREND_DOWN 230 đợt (mean 2h03m).
- Early Trend UP: 437 tín hiệu, 69.8% thành công, độ trễ trung bình 3.6 nến
  M15 (~54 phút); DOWN: 422 tín hiệu, 69.2%, 3.7 nến.
- Sideways breakouts: 80 (7 false).

> Các con số phản ánh model hiện tại trên dữ liệu demo 1 năm — là kết quả
> kiểm định ban đầu, không phải công bố tỷ lệ chính xác của hệ thống.

## 8. Testing

`backend/tests/test_history.py` (13 tests: segmentation, gap split, stats,
early trend, transition, daily split qua nửa đêm, multi-TF, compare,
**truncation invariance chống lookahead**) và `test_history_api.py` (job E2E,
toàn bộ endpoints, export CSV/XLSX/PDF). Toàn suite: 101 tests xanh.
