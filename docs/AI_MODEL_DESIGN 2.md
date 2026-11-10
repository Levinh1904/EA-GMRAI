# GMRAI — AI Model Design

## 1. Tổng quan pipeline huấn luyện

```
Candles (M15 + H1 + M5) ──► Features (versioned, no-lookahead)
        │
        ├──► Gaussian HMM (5 states) ──► filtered posterior (causal)
        │         └──► state mapping (thống kê trên train)
        │
        └──► Labels (future return, purge/embargo) ──► Random Forest
                  └── features: HMM posterior + market features + H1 + M5
        │
        ▼
Ensemble đánh giá OOS: HMM-only vs RF-only vs HMM+RF
        ▼
Regime Engine (thresholds tối ưu trên validation)
```

## 2. Gaussian HMM — Regime Detection

**Cấu hình chuẩn:**
- hmmlearn `GaussianHMM`, `n_components=5`, `covariance_type="diag"`, `n_iter=200`, `tol=1e-4`.
- Multistart: 10 lần init ngẫu nhiên với seed cố định, chọn model có log-likelihood train tốt nhất.
- Input: features M15 đã chuẩn hóa (scaler fit TRÊN TẬP TRAIN; mean/std lưu trong registry để tái lập).
- Train/validation/test: chia theo thứ tự thời gian, KHÔNG shuffle.

**Ánh xạ hidden state → semantic regime:**
HMM chỉ sinh hidden state không có nghĩa cố định. Với mỗi state, tính trên tập train (filtered posterior):
- Phân phối `ret1` (mean, std, skew).
- Volatility (ATR ratio trung bình).
- ADX trung bình, EMA slope trung bình, efficiency ratio.
- Duration trung bình (chuỗi liên tiếp theo filtered decode), occupancy, transition probability.

Sau đó ánh xạ bằng luật có ngưỡng:
| Bằng chứng | Regime |
|---|---|
| |ret1 mean| nhỏ, ATR ratio thấp, ADX thấp | SIDEWAYS |
| ret1 mean > +k·std, slope dương, hiệu quả cao | TREND_UP |
| ret1 mean < −k·std, slope âm, hiệu quả cao | TREND_DOWN |
| duration ngắn + transition cao + đặc tính trộn | TRANSITION |
| ATR ratio cao nhất nhóm, volatility lớn | HIGH_VOLATILITY |
| không đủ bằng chứng / mâu thuẫn | UNKNOWN (AMBIGUOUS) |

Kết quả mapping + bằng chứng thống kê lưu vào `hmm_models.state_mapping_json`. Không dùng dữ liệu validation/test để gán nhãn state.

**Causal inference (bắt buộc):**
- Chỉ dùng **filtered posterior** (forward algorithm); cấm Viterbi smoothing toàn chuỗi cho tín hiệu lịch sử.
- Tại thời điểm t chỉ dùng dữ liệu đến t.
- Engine suy luận chuẩn: `ml/hmm_inference.py` (`HmmFilter` thuần NumPy — tham chiếu cho port MQL5), parity test với hmmlearn (tol 1e-6).
- Warm-up: replay N nến M15 đã đóng gần nhất (mặc định 500) rồi lấy posterior cuối; kiểm tra inference sau restart.

**Early Trend:** không phải hidden state thứ 6. Suy ra từ: filtered posterior, transition matrix (xác suất chuyển vào state TREND), delta posterior theo thời gian, H1 context, feature xu hướng. Chỉ là cảnh báo nghiên cứu (EARLY_TREND_UP/DOWN), không cấp quyền giao dịch.

## 3. Random Forest — Supervised Regime Classifier

**Labels (target huấn luyện):**
- Tại thanh M15 đóng lúc t: `fwd_ret(t) = log(close[t+h] / close[t])` với h = 12 (≈3 giờ).
- Ngưỡng theo ATR(t) (chỉ dùng dữ liệu đã biết tại t):
  - `fwd_ret > +0.75·ATR14(t)` → TREND_UP
  - `fwd_ret < −0.75·ATR14(t)` → TREND_DOWN
  - còn lại → SIDEWAYS
- Label là target: không bao giờ đưa fwd_ret/close tương lai vào feature tại thời điểm dự đoán.
- Embargo h thanh giữa train/test khi chia dữ liệu để chống label leakage (purge khi dùng cửa sổ tương lai chồng lấn).

**Features của RF:**
1. HMM filtered posterior (5), state hiện tại (one-hot), max-posterior, entropy.
2. Thông tin transition: xác suất chuyển vào TREND_UP / TREND_DOWN từ state hiện tại.
3. Delta posterior 1-3 thanh (động lượng chuyển regime).
4. Market features M15 (ret1, ret4, atr_ratio, ema_slope, efficiency_ratio, adx_norm, di_gap).
5. H1 context (ema_slope, atr_ratio, adx_norm, trend_context).
6. M5 timing (ret_short, vol_ratio, momentum).

**Kiểm soát:** lookahead bias, label leakage (purge/embargo), class imbalance (class_weight balanced_subsample, đánh giá bằng F1/precision/recall — không chỉ accuracy), overfitting (validation time-split + walk-forward), hyperparameter tuning (grid trên validation, không tune trên test), feature importance (lưu vào registry), probability calibration (so sánh Brier score; calibrate nếu cải thiện trên validation).

**So sánh:** HMM-only (posterior→regime) vs RF-only vs HMM+RF trên tập test OOS; chỉ chọn ensemble nếu tốt hơn VÀ ổn định hơn (qua các fold walk-forward).

## 4. Regime Engine (operational)

Đầu vào: HMM posterior + semantic mapping + RF probabilities + H1 context + M5 timing.

Đầu ra (mỗi thanh M15 đóng):
- `regime` ∈ {SIDEWAYS, TREND_UP, TREND_DOWN, EARLY_TREND_UP, EARLY_TREND_DOWN, TRANSITION, HIGH_VOLATILITY, UNKNOWN}
- `confidence`, `probabilities` (HMM + RF), `reason_codes`, `expiry`, `permission` (BUY_ONLY / SELL_ONLY / NO_TRADE — chỉ là đầu ra nghiên cứu).

Cơ chế:
- **Threshold**: vào regime TREND_* khi xác suất tổng hợp ≥ θ_enter.
- **Hysteresis**: giữ regime tới khi xác suất < θ_exit (< θ_enter) để giảm lật trạng thái.
- **Confirmation**: yêu cầu k thanh liên tiếp thỏa điều kiện trước khi chuyển.
- **Confidence**: hàm của max posterior, entropy, sự đồng thuận HMM-RF.
- **Reason codes**: ví dụ `HMM_TREND_UP`, `RF_CONFIRM`, `H1_ALIGNED`, `LOW_CONFIDENCE`, `STALE_DATA`, `INFERENCE_FAILED`, `UNKNOWN_STATE`.
- θ_enter/θ_exit/k **tối ưu trên validation** (grid search theo F1 + false trend rate), kiểm tra trên test độc lập — không chọn ngưỡng cảm tính.

Nếu dữ liệu cũ (stale), model lỗi, feature không hợp lệ, inference thất bại → `UNKNOWN` / `NO_TRADE`.

## 5. Walk-forward validation

- Expanding window: train [0, t], test [t, t+H], lặp; hoặc rolling window kích thước cố định.
- Mỗi fold: retrain HMM + RF hoàn toàn (scaler, mapping, thresholds đều fit trên fold-train) → chống leakage tuyệt đối.
- Aggregate metrics trên các fold; stability = std của metrics giữa các fold.
- Trading simulation (nghiên cứu): vào lệnh theo permission tại close thanh, thoát khi regime đổi/hết horizon; trừ spread+commission giả định; metrics: profit factor, max drawdown, expectancy, win rate, average R, opportunities, missed trends.
