# GMRAI — Data Pipeline

## 1. Luồng dữ liệu

```
MT5 → Collector → Ingestion API → market_candles
        │
        ▼
Quality checks (định kỳ + sau mỗi sync) → data_quality_reports
        │
        ▼
Feature engineering (M15 + H1 + M5) → market_features (feature_version)
        │
        ▼
Training / Inference / Backtest
```

## 2. Quy tắc dữ liệu (bắt buộc)

- Chỉ dùng **nến đã đóng** ở mọi bước.
- Không tự tạo dữ liệu giả thay dữ liệu thiếu. Dữ liệu demo phục vụ dev được gắn `source=synthetic_demo` và hiển thị nhãn rõ ràng.
- Timestamp UTC; unique `(symbol, timeframe, ts)`; upsert khi trùng.
- Resync N nến gần nhất (mặc định 50) mỗi chu kỳ để xử lý cập nhật muộn.
- Kiểm tra: số nến thực tế, gap, duplicate, candle lỗi (high<low, OHLC không dương, spread < 0), stale (nến mới nhất quá cũ so với hiện tại).
- Nếu ingestion thất bại → collector retry + checkpoint, không mất dữ liệu.

## 3. Feature engineering (M15 là khung chính)

Tất cả feature tính tại thời điểm đóng thanh M15 `t`, chỉ dùng dữ liệu ≤ t.

### 3.1 Features M15

| Feature | Công thức | Ý nghĩa |
|---|---|---|
| ret1 | log(close[t]/close[t-1]) | return 1 thanh |
| ret4 | log(close[t]/close[t-4]) | return 4 thanh |
| atr_ratio | ATR14(t) / SMA20(ATR14) | volatility regime (co giãn) |
| ema_slope | (EMA20[t] − EMA20[t-4]) / ATR14(t) | độ dốc xu hướng chuẩn hóa |
| efficiency_ratio | |net move 10 thanh| / Σ|bar move| 10 thanh | hiệu suất biến động |
| adx_norm | ADX14(t) / 100 | sức mạnh xu hướng |
| di_gap | (+DI14 − −DI14) / 100 | hướng xu hướng |

ATR = Wilder smoothing (EMA, α=1/14) của TR; ADX/±DI theo Wilder chuẩn (giá trị gốc 0-100 → chuẩn hóa /100).

### 3.2 Context H1 (nối vào từng thanh M15)

- `h1_ema_slope`: độ dốc EMA20 H1 (4 thanh H1) / ATR14 H1.
- `h1_atr_ratio`: ATR ratio H1.
- `h1_adx_norm`: ADX14 H1 / 100.
- `h1_trend_context`: hướng trend H1 = sign(close − EMA20) · adx_norm (dương = uptrend mạnh).

Sử dụng thanh H1 đã đóng **gần nhất trước/đúng thời điểm t** (chỉ nến đóng).

### 3.3 Timing M5

- `m5_ret_short`: return 6 thanh M5 gần nhất (≈30 phút).
- `m5_vol_ratio`: volatility ngắn (6 thanh M5) / volatility dài (36 thanh M5).
- `m5_momentum`: (close M5 − SMA12 M5) / ATR14 M5.

Chỉ dùng thanh M5 đã đóng trước/đúng t.

### 3.4 Quy tắc chung

- NaN: thanh đầu không đủ dữ liệu → feature NaN → loại khỏi training/inference (feature row bị drop, không điền bừa); Inf → thay bằng NaN rồi drop.
- Outlier: clip theo phân vị 0.5–99.5 của **train** (ngưỡng lưu vào feature spec để tái lập).
- Scaler (StandardScaler): fit trên train only; mean/std lưu trong model registry.
- Feature version: `v1` — mọi thay đổi công thức phải tăng version, không ghi đè cũ.

## 4. Split dữ liệu (chống leakage)

- Chronological split: train → validation → test theo thời gian. Không shuffle.
- Purge/embargo: label dùng tương lai h thanh → khi chia, loại bỏ (purge) phần chồng lấn và đặt embargo h thanh giữa các tập.
- Walk-forward: expanding/rolling window; mỗi fold fit lại toàn bộ (scaler, HMM, RF, mapping, thresholds).

## 5. Staleness

- `GMRAI_MAX_DATA_AGE_MINUTES` (mặc định: M15 → 60 phút, M5 → 30 phút, H1 → 180 phút).
- Nếu nến mới nhất cũ hơn ngưỡng → regime trả `UNKNOWN` + reason `STALE_DATA`.
