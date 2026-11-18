# trade_ens — model mới trong GMRAI hiện tại

Tài liệu này mô tả phần được thêm vào project GMRAI **hiện tại**. Không có project mới,
không có database mới, không xoá HMM/RF cũ. `trade_ens` chạy song song và có API/trang riêng.

## 1. Phạm vi

- Một tên model duy nhất: `trade_ens` (LightGBM + RandomForest + LogisticRegression).
- Dữ liệu: nến thật `ftmo_mt5` đang có trong `market_candles` (M5/M15/H1).
- Output: `LONG`, `SHORT`, `NO_TRADE` tại close của nến M15 đã đóng.
- Không gửi lệnh MT5, không quản lý vốn, không có endpoint đặt lệnh.
- Không dùng HMM, RF-regime, HSMM, BOCPD hay ONNX trong `trade_ens`. Các model regime cũ
  vẫn tồn tại độc lập cho các trang cũ; không được trộn probability của chúng vào model này.

## 2. Feature Schema v2 — 37 cột

Nguồn: `backend/app/ml/features_v2.py`.

- 7 M15 cơ bản: `ret1, ret4, atr_ratio, ema_slope, efficiency_ratio, adx_norm, di_gap`
- 4 H1 context: `h1_ema_slope, h1_atr_ratio, h1_adx_norm, h1_trend_context`
- 3 M5 context: `m5_ret_short, m5_vol_ratio, m5_momentum`
- 21 M15 mở rộng: DI, EMA50, persistence, displacement, consistency, ATR/vol, RSI, momentum,
  candle body/wick, breakout, range compression/expansion
- 2 thời gian: `hour_sin, hour_cos` (UTC)

Mọi feature tại nến `t` chỉ dùng dữ liệu đã đóng tại `t`. H1/M5 được join bằng **close time**
(`asof_closed`), không phải open time. Test `test_truncating_future_candles_does_not_change_past_features`
kiểm tra không rò rỉ tương lai.

## 3. Barrier label

Nguồn: `backend/app/ml/profit_trader.py`.

- Entry: `open[t+1]`
- TP: `0.5 × ATR14`, SL: `2.0 × ATR14`
- Horizon: 16 nến M15
- LONG và SHORT được mô phỏng **độc lập** (hai đường barrier riêng).
- Nếu một nến chạm cả TP và SL: tính **SL trước** (conservative).
- PnL trừ spread của nến signal (`spread_points × $0.01`).
- Nến không đủ horizon hoặc gặp gap > 1.5 nến: outcome invalid, không dùng train/test.

Hệ quả: win-rate cao là bình thường vì TP gần hơn SL 4 lần. Win-rate **không phải lợi nhuận**;
breakeven win-rate thực tế quanh 82% trong lần chạy này.

## 4. Walk-forward và threshold

Nguồn: `backend/app/ml/trade_model.py`.

- 4 fold test liên tiếp, mỗi block tối đa 3500 nến; holdout cuối tối đa 480 nến.
- Mỗi fold: train 65%, early-stop 15%, selection 20%; embargo 30 nến giữa các phần.
- Threshold chọn trên **selection only** từ q ∈ {0.02, 0.05, 0.10, 0.20, 0.30, 0.50},
  yêu cầu tối thiểu **50 lệnh** mỗi fold và win-rate ≥ 70%; chọn q có mean PnL cao nhất.
- Model hiện tại chỉ cho phép **SHORT**. Lý do chọn trên selection folds: khi tối ưu
  threshold riêng, LONG-only có mean PnL âm ở 3/4 fold; SHORT-only dương ở 4/4 fold.
  Holdout không được dùng để chọn side/threshold.
- Gate deploy mới (bắt buộc lợi nhuận): `n ≥ 300`, `mean PnL > 0`, `PF > 1`,
  `win_rate > breakeven`, và `Wilson low ≥ breakeven`.
- Holdout chỉ chấm một lần, không dùng để chọn threshold.
- Không có test-set tuning.

## 5. Kết quả thật của model version 14 (SHORT-only)

Dữ liệu: `ftmo_mt5`, 23,915 feature rows, 21,392 valid barrier rows.

| Tập | n | Win rate | Wilson low | Mean PnL/oz | Total PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| OOS 4 fold | 426 | 85.21% | 81.53% | **+0.956** | **+407.26** | 1.368 | −89.77 |
| Holdout 480 nến | 0 | — | — | — | — | — | — |

- Breakeven win-rate OOS: 80.81%. Wilson low 81.53% > breakeven; gate lợi nhuận **pass**.
- 3 fold dương (+179.57, +157.91, +79.59), 1 fold âm nhẹ (−9.81); pooled vẫn dương.
- Holdout không có lệnh tại threshold đã đóng băng (`SHORT=0.818800`), nên **vẫn không có
  bằng chứng PnL holdout**. Đây là hạn chế thật, không được bỏ qua.
- In-sample replay của final model dương nhưng chỉ dùng để debug, không phải track record.
- Các version 11/12/13 (thử nghiệm) đã archive; version 14 là bản approved duy nhất.
  Nếu muốn bật lại LONG, phải dùng validation riêng và gate lại từ đầu.

Đây là kết quả thật của code + dữ liệu hiện tại; không phải số mô phỏng.

## 6. API

Các endpoint mới (đều cần Bearer token):

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/v1/trade-model/status` | approved model + OOS/holdout metrics |
| GET | `/api/v1/trade-model/deployability` | model gate + data freshness + blockers; `demo_ready`/`live_ready` |
| GET | `/api/v1/trade-model/signal` | tín hiệu mới nhất, cache 15s, có `tradeable` |
| GET | `/api/v1/trade-model/history?limit=300` | replay in-sample, không phải live track record |
| POST | `/api/v1/trade-model/train` | admin-only, chạy background job |
| GET | `/api/v1/reference/latest` | rule-based `ref_v1`, **không phải model** |
| GET | `/api/v1/reference/history` | lịch sử context ref_v1 |
| GET | `/api/v1/features?version=v2&limit=...` | feature v2 tính causal từ nến |

`/trade-model/signal` trả `409` với code `NO_APPROVED_MODEL` nếu chưa có model,
`DEMO_DATA_NOT_SUPPORTED` nếu chỉ có `synthetic_demo`. Không tự bịa tín hiệu.

## 7. UI

- Trang mới: `/signals` — “Trade Ens”.
- Hiển thị trạng thái model, allowed sides, threshold, OOS/holdout, tín hiệu hiện tại,
  replay in-sample và cảnh báo win-rate ≠ profit.
- Nút “Train trade_ens” chỉ hiện với admin.
- Khi HMM/RF bị archive và chỉ còn `trade_ens`, `/regime/latest` và dashboard trả
  `regime = TRADE_ENS` + `engine = trade_ens` kèm link `/signals`, **không còn UNKNOWN**.
  Đây là fallback hiển thị rõ, không map trade_ens thành TREND_UP/TREND_DOWN giả.

## 8. Database và registry

Không thêm migration. Dùng lại:

- `training_runs` với `model_type = 'trade_ens'`, `feature_version = 'v2'`
- `model_versions` với `model_type = 'trade_ens'`, artifact joblib
- `model_versions.metrics_json` chứa walk-forward, holdout, warnings
- Artifact: `artifacts/trade_ens/<timestamp>/model.joblib`

Registry cũ vẫn giữ nguyên state machine `approved → archived` (không `approved → rejected`).

## 9. Chạy lại

```bash
cd backend
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Training qua UI `/signals` hoặc:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/trade-model/train \
  -H "Authorization: Bearer <token>"
```

Frontend hiện chạy ở `http://localhost:3010` với
`NEXT_PUBLIC_API_URL=http://localhost:8010` (không dùng 3000/8000).

MacOS cần `libomp` cho LightGBM. Nếu import báo thiếu `libomp.dylib`, cài bằng
`brew install libomp` (hoặc dùng libomp đi kèm scikit-learn trong cùng venv).
`trade_model.py` báo lỗi rõ ràng nếu LightGBM không load được, không âm thầm thay bằng model khác.

## 10. Kiểm thử

- `tests/test_features_v2.py` — 37 cột, causal, truncation.
- `tests/test_profit_trader.py` — barrier LONG/SHORT độc lập, SL-first, one-position policy,
  SHORT-only không bị p(LONG) cao ép tín hiệu.
- `tests/test_trade_model.py` — 4 fold liên tiếp, holdout không bị dùng.
- `tests/test_trade_api.py` — no-model trả code rõ ràng, admin-only training.
- `/trade-model/deployability` trả `demo_ready`, `live_ready`, blockers; không tự biến stale data
  thành ready.

Thực tế đã chạy: 13 test mới pass; toàn bộ backend suite 292 test pass; frontend `typecheck` và
`build` pass (có route `/signals`).

## 11. Giới hạn trung thực

- Model gate pass (OOS 426 lệnh, +407.26, PF 1.37) → **demo_ready = true**.
- **live_ready = false** khi dữ liệu M15 stale (bar cuối 2026-11-16 17:45, thiếu feed).
  Collector/MT5 phải cập nhật nến thật; không được thay bằng nguồn khác hoặc synthetic.
- Holdout 480 nến không có lệnh, nên chưa có kiểm chứng PnL ngoài mẫu cho threshold cuối.
- Chưa có forward shadow; endpoint ghi warning `NO_FORWARD_SHADOW`.
- Model hiện tại là SHORT-only, 426 lệnh OOS; đây là mẫu một năm, không phải edge vĩnh viễn.
- OOS dương **không** đảm bảo live dương. Spread/slippage live có thể xấu hơn spread trong nến.
- Risk/lệnh và max daily loss do EA xử lý; API chỉ trả tín hiệu + `tradeable` + cảnh báo stale.
- Không dùng holdout để chỉnh threshold, side filter hay chọn feature.
