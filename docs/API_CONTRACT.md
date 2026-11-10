# GMRAI — API Contract (v1)

Base URL: `{host}/api/v1`. Auth: `Authorization: Bearer <JWT>` cho mọi
endpoint (trừ ingestion dùng `X-API-Key` và health không cần auth).

## Auth

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/auth/login` | — (rate limit 5/phút) | `{"username","password"}` → `{"access_token","token_type","username","role"}` |
| GET | `/auth/me` | JWT | thông tin user hiện tại |

## Ingestion (collector)

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/ingest/candles?timeframe=M5\|M15\|H1` | `X-API-Key` | upsert batch nến đã đóng (≤10.000/req). Body `{"candles":[{symbol,ts,open,high,low,close,tick_volume,spread,real_volume,source}]}` → `{"status","collector_id","received","inserted","updated","rejected"}` |
| GET | `/ingest/status` | JWT | sync logs gần đây |

## Market

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/market/candles?timeframe&symbol&from&to&limit&offset` | JWT | paginated candles (asc) |
| GET | `/market/latest` | JWT | nến mới nhất M5/M15/H1 |

## Regime (nghiên cứu — không phải tín hiệu giao dịch)

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/regime/latest?symbol=XAUUSD` | JWT | xem cấu trúc dưới |
| GET | `/regime/history?limit=500` | JWT | lịch sử regime |

`/regime/latest` response:

```json
{
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "timestamp": "2026-11-09T16:04:00+00:00",
  "regime": "SIDEWAYS",
  "confidence": 0.6868,
  "probabilities": {
    "hmm_semantic": {"SIDEWAYS": 0.999, "TREND_DOWN": 0.0, "UNKNOWN": 0.001},
    "rf": {"SIDEWAYS": 0.415, "TREND_DOWN": 0.259, "TREND_UP": 0.326}
  },
  "model_version": 1,
  "feature_version": "v1",
  "data_timestamp": "2026-11-09T16:19:00+00:00",
  "data_source": "synthetic_demo",
  "expiry": "2026-11-09T16:34:00+00:00",
  "reason_codes": ["RF_HMM_DIVERGE"],
  "permission": "NO_TRADE",
  "data_age_minutes": 17.1
}
```

- `regime` ∈ {SIDEWAYS, TREND_UP, TREND_DOWN, EARLY_TREND_UP, EARLY_TREND_DOWN,
  TRANSITION, HIGH_VOLATILITY, UNKNOWN}.
- `permission` ∈ {BUY_ONLY, SELL_ONLY, NO_TRADE} — **đầu ra nghiên cứu**;
  GMRAI không có endpoint gửi lệnh.
- Dữ liệu cũ / model lỗi / inference fail ⇒ `UNKNOWN` + `NO_TRADE` +
  reason codes tương ứng (STALE_DATA, NO_APPROVED_MODEL, INFERENCE_FAILED...).
- `expiry`: tín hiệu hết hiệu lực sau 2 thanh M15.
- EA nên kiểm tra `data_age_minutes` và `expiry` trước khi dùng.

## Features / Quality

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/features?timeframe&limit&offset&feature_version` | JWT | features đã tính |
| GET | `/quality/reports?limit` | JWT | báo cáo chất lượng dữ liệu |
| POST | `/quality/run` | admin | chạy quality check M5/M15/H1 |

## Training / Backtest (async jobs)

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/training/runs?limit` | JWT | danh sách training runs |
| POST | `/training/run` | admin | body (optional): `{hmm_n_states,hmm_n_init,seed,train_frac,val_frac,rf_horizon,up_threshold_atr,weight_hmm}` → `{"status":"scheduled","job_id"}` |
| GET | `/training/runs/{id}` | JWT | trạng thái + metrics |
| GET | `/backtests?limit` | JWT | danh sách backtest runs |
| POST | `/backtests` | admin | body `{name,initial_train,test_size,embargo,hmm_n_states,hmm_n_init,rf_horizon,up_threshold_atr,cost_usd,max_hold}` → `{"status":"scheduled","job_id"}` |
| GET | `/backtests/{id}` | JWT | config + metrics (variant_comparison) |

## Model Registry

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/models?model_type=hmm\|random_forest&limit` | JWT | danh sách versions |
| GET | `/models/{version_id}` | JWT | chi tiết + metrics |
| POST | `/models/{version_id}/status` | admin | body `{"status":"approved\|rejected\|archived","force":bool}` — transitions được guard |
| GET | `/models/{version_id}/download` | JWT | artifact (joblib/json) |
| GET | `/models/{version_id}/onnx` | JWT | file ONNX (random_forest) |
| POST | `/models/{version_id}/export-onnx` | admin | (re)export ONNX + parity check |

## Stats / System / Health

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/stats/dashboard` | JWT | tổng hợp overview |
| GET | `/system/status` | JWT | candles, active models, recent jobs |
| GET | `/system/logs?limit` | JWT | system logs |
| GET | `/health` hoặc `/api/v1/health` | — | `{"api","database","worker"}` |

## Historical Regime Analyzer (module mới)

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| POST | `/history/run` | admin | chạy phân tích lịch sử (job nền) → `{"status","run_id"}` |
| GET | `/history/runs` | JWT | danh sách runs |
| GET | `/history/runs/{id}` | JWT | chi tiết run |
| GET | `/history/runs/{id}/bars?limit&offset` | JWT | nến + AI regime + **reference regime/reason/indicators** từng thanh (causal) |
| GET | `/history/runs/{id}/segments?regime&min_duration&max_duration&limit&offset` | JWT | danh sách regime segments |
| GET | `/history/runs/{id}/segments/{seg_id}` | JWT | chi tiết segment |
| GET | `/history/runs/{id}/stats/duration` | JWT | thống kê thời lượng mỗi regime |
| GET | `/history/runs/{id}/stats/trends` | JWT | trend analysis + phân loại mạnh/yếu (quantile) |
| GET | `/history/runs/{id}/stats/sideways` | JWT | sideways analysis + buckets + breakouts |
| GET | `/history/runs/{id}/stats/early_trend?window=12` | JWT | đánh giá Early Trend vs reference labels |
| GET | `/history/runs/{id}/stats/transitions` | JWT | ma trận chuyển trạng thái vận hành |
| GET | `/history/runs/{id}/stats/periods?period=day\|week\|month\|quarter\|year` | JWT | tổng hợp theo chu kỳ |
| GET | `/history/runs/{id}/stats/multi_tf` | JWT | so sánh M15 regime vs H1 context + M5 timing |
| GET | `/history/runs/{id}/stats/vs_reference` | JWT | AI vs Reference: agreement, confusion full-class, per-class+macro F1, false trend/sideways rate, detection delay, boundary & duration disagreement |
| GET | `/history/runs/{id}/stats/outcomes` | JWT | kết quả tương lai (12/48/96 nến) theo từng regime — đánh giá, không đổi prediction |
| GET | `/history/runs/{id}/compare?vs_run_id=N` | JWT | so sánh 2 runs (agreement, confusion) |
| GET | `/history/runs/{id}/compare?vs_reference=true` | JWT | đánh giá vs reference labels độc lập |
| GET | `/history/runs/{id}/export?format=csv\|xlsx\|pdf&scope=segments\|bars\|report` | JWT | xuất CSV/Excel/PDF |

Nguyên tắc module: per-bar regime được tính **causal** (filtered posterior, không smoothing); reference labels (realized forward returns) chỉ dùng để ĐÁNH GIÁ sau, không tạo tín hiệu; segments không gộp qua lỗ hổng dữ liệu (`split_reason=data_gap`); không trộn nguồn dữ liệu (run chọn `ftmo_mt5` nếu có, nếu không thì `synthetic_demo` được ghi rõ).

## Lỗi

- 401 thiếu/sai token hoặc API key; 403 thiếu quyền; 404 không tìm thấy;
  422 input không hợp lệ (nến đang hình thành, OHLC sai...);
  429 vượt rate limit. Response JSON: `{"detail": "..."}`.
