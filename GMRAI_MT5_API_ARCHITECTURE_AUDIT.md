# GMRAI — MT5 API Architecture Audit

**Ngày kiểm toán:** 2026-11-17  
**Phạm vi:** backend GMRAI hiện tại trong repo `GMRAI/` (không gồm frontend, collector MT5 chạy Windows, và không gồm code EA/MQL5 vì repo chưa có).  
**Mục đích:** đánh giá khả năng tích hợp GMRAI với MT5 EA qua API, làm rõ phần đã có / còn thiếu, đề xuất API contract và schema để chuẩn bị triển khai.  
**Tính chất:** kiểm toán read-only. Tài liệu này **không thay đổi source code**, không tạo migration, không thêm endpoint, không sửa schema. Mọi mục đánh dấu `[PROPOSED]` là thiết kế đề xuất, chưa tồn tại trong code.

**Quy ước trạng thái**

| Nhãn | Nghĩa |
|---|---|
| `[VERIFIED]` | Đã xác minh trực tiếp trong code/DB hiện tại, có dẫn chứng file:line |
| `[PARTIAL]` | Có một phần cơ chế tương tự, nhưng chưa đủ cho EA production |
| `[MISSING]` | Không tìm thấy trong code/DB hiện tại |
| `[PROPOSED]` | Thiết kế mới, chưa được implement |

---

## 0. Kết luận điều hành

1. **GMRAI hiện tại là hệ thống nghiên cứu regime theo từng nến, không phải hệ thống phát event giao dịch.** Nó lưu `ModelPrediction` cho từng bar M15 với `regime`, `permission`, `confidence`, `expiry_ts`, nhưng **không có** `trend_id`, `event_id`, `sequence_id`, `END_UP`, `END_DOWN`, `CANCEL_UP`, `CANCEL_DOWN`, event history hay execution feedback. `[VERIFIED]`
2. **EA không nên đọc trực tiếp `/regime/latest` như một event stream.** Endpoint này là snapshot request-driven, có cache 5 giây; client chỉ có thể suy ra chuyển trạng thái bằng cách tự so sánh các snapshot, nên dễ bỏ lỡ chuyển đổi hoặc xử lý sai thứ tự. `[VERIFIED]`
3. **Không có lớp execution/order.** Repo không có bảng EA instance, order, execution, heartbeat, ack/cursor, audit cho EA. Collector MT5 chỉ gửi nến/tick lên server, không gửi lệnh. `[VERIFIED]`
4. **Xác suất hiện có không phải xác suất thắng lệnh.** `p_up/p_down/p_side` là xác suất lớp regime từ HMM/RF; `confidence` là xác suất lớp có điều chỉnh agreement. Không có `p_win`, expected value hay xác suất TP/SL. Module forecast nến kế tiếp còn ghi rõ accuracy ~0.4967, AUC ~0.5169, “no exploitable edge”. `[VERIFIED]`
5. **Để tích hợp EA an toàn cần một lớp event-sourced mới**: event publisher, trend lifecycle, sequence/cursor, snapshot, EA authentication/scope, execution feedback, heartbeat và audit. Phần này chưa có. `[MISSING]` + `[PROPOSED]`
6. **Khuyến nghị kiến trúc:** GMRAI giữ vai trò **signal/research provider**, EA là bên **duy nhất gửi lệnh** tới broker. GMRAI nhận execution feedback và heartbeat từ EA, không giữ mật khẩu broker và không có endpoint gửi lệnh. Cách này giảm rủi ro pháp lý/vận hành và phù hợp với tuyên bố research-only hiện tại. `[PROPOSED]`

---

## 1. Kiến trúc thực tế hiện tại

### 1.1 Ngôn ngữ, framework, thành phần

| Thành phần | Công nghệ / file | Trạng thái |
|---|---|---|
| Backend API | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic; app factory tại `backend/app/main.py:83` | `[VERIFIED]` |
| ML | NumPy, pandas, scikit-learn (`RandomForestClassifier`), hmmlearn (`GaussianHMM`), ONNX export | `[VERIFIED]` |
| Database | SQLite cho dev/test, PostgreSQL 16 cho production qua `GMRAI_DATABASE_URL`; engine/session tại `backend/app/db.py:19-32`; compose Postgres tại `docker-compose.yml:1-15` | `[VERIFIED]` |
| Collector | Python + thư viện MetaTrader5 trên Windows; main loop `collector/collector.py:81-159`, gửi nến `collector/collector.py:123`, gửi tick `collector/collector.py:72` | `[VERIFIED]` |
| Frontend | Next.js/TypeScript (không thuộc phạm vi backend audit) | `[VERIFIED]` |
| EA/MQL5 | **Chưa có trong repo** | `[MISSING]` |

### 1.2 Cấu trúc backend

```
backend/app/
├── main.py                 FastAPI app, lifespan, health, CORS, rate-limit
├── config.py               Settings (env prefix GMRAI_)
├── db.py                   Engine/session SQLAlchemy
├── deps.py                 JWT user auth, admin guard, ingestion API key
├── models/models.py        ORM schema
├── routers/                auth, ingest, market, features, quality, training,
│                           backtest, registry, onnx, regime, history, stats,
│                           telegram, forecast, admin, jobs
├── services/               prediction, history, registry, training, worker,
│                           ingestion, forecast, telegram, retention, ...
├── ml/                     features, labels, HMM, RF, regime engine,
│                           state detector, backtest, evaluation, ONNX
├── security/auth.py        JWT + password/API-key hash
└── worker_main.py          Worker process entry point
```

- Route prefix versioned `/api/v1` tại `backend/app/routers/__init__.py:19-38`.
- API chính gồm auth, ingestion, market, features, quality, training, backtest, model registry, ONNX, regime, history, stats/system, Telegram, forecast, admin, jobs; danh sách route đầy đủ nằm trong các file `backend/app/routers/*.py`.
- Không có namespace `/ea`, `/events`, `/executions` hay `/heartbeat` trong route hiện tại. `[VERIFIED — route grep toàn backend/app/routers]`

### 1.3 Database đang dùng

Các bảng hiện có (theo ORM `backend/app/models/models.py` và DB SQLite đang chạy):

| Nhóm | Bảng | Dẫn chứng |
|---|---|---|
| Người dùng / auth | `users`, `api_keys` | `models.py:22-42` |
| Dữ liệu thị trường | `market_candles`, `data_sync_logs`, `data_quality_reports`, `market_features`, `market_ticks` | `models.py:45-136`, `models.py:362-376`; `services/ingestion.py:25-...` |
| Model registry | `hmm_models`, `random_forest_models`, `model_versions` | `models.py:139-185` |
| Dự báo / lịch sử | `model_predictions`, `bar_forecasts`, `telegram_messages` | `models.py:188-210`, `models.py:411-480` |
| Jobs / logs | `training_runs`, `backtest_runs`, `backtest_metrics`, `background_jobs`, `system_logs` | `models.py:213-280` |
| Historical Analyzer | `regime_history_runs`, `regime_history_bars`, `outcome_evaluations`, `regime_segments` | `models.py:283-408` |
| Migration | Alembic versions `9acf55d431bb_initial_schema.py`, `4f1c9b7a2d10...`, `36239d14870a...`, `6618ec2544f0...`, `8ab6ee0542c9...`, `2602a6d956cc...`, `9d3e5a1b7c42...` | `backend/alembic/versions/` |

**Không có bảng** `events`, `signal_events`, `trend_states`, `ea_instances`, `execution_orders`, `execution_history`, `ea_heartbeats`, `api_audit_logs`, `event_outbox`, `state_snapshots`, `ea_cursors`. `[VERIFIED — .tables và models.py]`

### 1.4 Cách GMRAI nhận và xử lý dữ liệu thị trường

1. Collector Windows đọc nến đã đóng M5/M15/H1 từ MT5 và gửi HTTP batch tới `POST /api/v1/ingest/candles` bằng `X-API-Key` (`collector/collector.py:81-159`, `backend/app/routers/ingest.py:14-33`, `collector/README.md:1-11`).
2. Ingestion validate OHLC, từ chối nến đang hình thành, upsert theo nguồn (`backend/app/services/ingestion.py:25-...`; `CandleIn` tại `backend/app/schemas.py:10-24`), ghi `data_sync_logs`.
3. Tick Bid/Ask chỉ để hiển thị, gửi qua `POST /api/v1/market/tick` (`backend/app/routers/market.py:113-136`); endpoint GET yêu cầu JWT (`market.py:138-...`). Collector nhấn mạnh không gửi lệnh (`collector/README.md:10-11`).
4. Dữ liệu nến được dùng để build features M15/H1/M5; scaler và feature version nằm trong artifact/model (`backend/app/ml/features.py`, `backend/app/services/training.py`).
5. Backend từ chối khởi động nếu secret yếu (`app/config.py:116-134`) và health probe kiểm tra API/DB/worker (`app/main.py:110-159`).

### 1.5 Quản lý model và phiên bản

- Model registry dùng `ModelVersion` với `model_type` (`hmm`/`random_forest`), `model_id`, `version`, `status`, `metrics_json`, `artifact_path` (`models.py:175-185`).
- State machine chỉ cho các chuyển hợp lệ: candidate→approved/rejected, approved→archived, rejected→archived/candidate, archived→candidate, training/validating→candidate/rejected (`services/registry.py:13-54`).
- Active pair được chọn theo `model_id` chung giữa HMM và RF, tránh ghép lệch training run (`services/registry.py:73-97`).
- Training tạo artifact HMM JSON + RF joblib/ONNX, kiểm tra parity ONNX (`services/training.py`, `ml/onnx_export.py`).
- Hiện DB dev có models 9/10 approved, 5/6 archived, 7/8 candidate; đây là trạng thái vận hành, không phải hằng số code. `[VERIFIED — DB query]`

### 1.6 Cách lưu kết quả dự báo

- `ModelPrediction` lưu một dòng cho mỗi `(model_version_id, symbol, timeframe, ts)`; UNIQUE constraint `uq_pred_bar` (`models.py:188-210`).
- Các trường chính: `regime`, `confidence`, `probabilities_json` (HMM semantic + RF + combined), `components_json` (engine_state, raw_regime, model_versions, detected_state...), `reason_codes_json`, `permission`, `expiry_ts`, `data_timestamp`.
- Prediction được tạo trong `compute_latest_regime` (`services/prediction.py:123-365`), lưu với `expiry_ts = feature_ts + 2*M15` (`prediction.py:331`).
- Polling lặp cho cùng bar trả bản ghi cũ, không chạy lại engine (`prediction.py:144-167`, `_find_prediction` tại `prediction.py:75-93`).
- Khi app downtime, worker gọi `backfill_predictions` để điền các bar thiếu (`services/prediction.py:389-...`, worker `services/worker.py:169-...`).
- Retention có thể xoá `model_predictions` sau 365 ngày (`services/retention.py:59-...`, `config.py:71-72`).

**Kết luận mục 1:** backend hiện có pipeline dữ liệu → model → regime → snapshot per bar, nhưng lưu **prediction**, không lưu **event/trend lifecycle**. `[VERIFIED]`

---

## 2. Cơ chế phát tín hiệu hiện tại

### 2.1 Bảng đối chiếu chức năng yêu cầu

| Chức năng | Hiện trạng | Dẫn chứng / kết luận |
|---|---|---|
| Phát hiện UP | `[PARTIAL]` Có regime `TREND_UP` và detector `TREND_UP`; engine vào trend qua hysteresis/confirm hoặc state override | `backend/app/ml/state_detector.py:93-142`; `regime_engine.py:264-321`, `371-388` |
| Phát hiện DOWN | `[PARTIAL]` Tương tự, `TREND_DOWN` | `state_detector.py:93-142`; `regime_engine.py:248-263`, `290-314` |
| END_UP | `[MISSING]` Không có event/type; engine chỉ chuyển state về `base` và ghi reason `EXIT_BELOW_THRESHOLD` | `regime_engine.py:232-247` (exit logic), không có symbol `END_UP` trong backend/app |
| END_DOWN | `[MISSING]` Tương tự | `regime_engine.py:248-263` |
| CANCEL_UP | `[MISSING]` Không có khái niệm cancel/ack; chỉ có `SIGNAL_FILTERED_*`, `LONG_FILTERED_*`, `HOUR_FILTERED` tại thời điểm entry | `regime_engine.py:266-302`, `390-395`; grep `CANCEL_` không có kết quả |
| CANCEL_DOWN | `[MISSING]` Tương tự | `regime_engine.py:290-302` |
| `trend_id` | `[MISSING]` Không có cột/table/field; `RegimeSegment.segment_index` chỉ là index trong một history run, không phải identity live | `models.py:379-408`; `ml/history.py:163-...`; `models.py:188-210` không có trend_id |
| Thời điểm phát tín hiệu | `[PARTIAL]` Request-driven khi gọi `/regime/latest`; worker backfill định kỳ; không có push/event emit | `routers/regime.py:13-21`; `services/prediction.py:654-687`; `worker.py:135-185` |
| Xác suất model cung cấp | `[VERIFIED]` HMM posterior semantic + RF 3-class + combined probability/agreement; **không có xác suất thắng lệnh** | `regime_engine.py:85-114`; `hmm_model.py:241-...`; `rf_model.py:147-...`; `regime_engine.py:124-146` |

### 2.2 Luồng regime hiện tại

- HMM trả posterior đã lọc (causal, forward-only) cho các state; `semantic_probabilities` cộng posterior theo state mapping thành `TREND_UP`, `TREND_DOWN`, `SIDEWAYS`, `TRANSITION`, `HIGH_VOLATILITY` (`ml/hmm_model.py:241-...`; `ml/hmm_inference.py:19-66`).
- RF nhận HMM posterior/transition + feature thị trường và trả xác suất 3 lớp `TREND_DOWN`, `SIDEWAYS`, `TREND_UP` (`rf_model.py:54-86`, `147-154`).
- `combine_scores` trộn có trọng số, chuẩn hoá 5 nhóm xác suất và tính `agreement` (`regime_engine.py:85-114`).
- `EngineState.step` dùng `theta_enter/theta_exit`, `confirm_bars`, `min_hold_bars`, `min_signal_bars`, session filter, displacement/H1 gate, state detector override; trả `regime`, `confidence`, `reason_codes`, `engine_state` (`regime_engine.py:177-406`).
- `PERMISSIONS` chỉ map `TREND_UP→BUY_ONLY`, `TREND_DOWN→SELL_ONLY`; mọi regime khác `NO_TRADE` (`regime_engine.py:31`). Đây là **permission nghiên cứu**, không phải lệnh thật.
- `EARLY_TREND_UP/DOWN` là advisory, không đổi state machine, và theo `PERMISSIONS` là `NO_TRADE` (`regime_engine.py:323-342`; `PERMISSIONS` line 31).
- `END` hiện tại chỉ là việc engine trả về `SIDEWAYS/TRANSITION/...`; không có record event, không có `trend_id`, không có thời điểm end chính thức. Client phải tự diff hai prediction liên tiếp.
- `CANCEL` hiện tại không tồn tại; các lý do `LONG_FILTERED_*`, `HOUR_FILTERED`, `SIGNAL_FILTERED_*` chỉ là reason code tại thời điểm entry, không phải event gửi EA.

### 2.3 Xác suất: phân biệt rõ

**Xác suất phát hiện xu hướng hiện có**

- `p_up`, `p_down`, `p_side`, `p_trans`, `p_highvol` trong `combine_scores` là xác suất lớp regime sau khi trộn HMM và RF (`regime_engine.py:85-114`).
- `confidence` là `_class_confidence(regime,row)`: lấy xác suất lớp tương ứng nhân hệ số agreement, cap 1.0 (`regime_engine.py:124-146`). Đây **không phải** xác suất lệnh thắng, không phải expected value, không phải xác suất TP/SL.
- `model_predictions.probabilities_json` lưu HMM semantic, RF và combined (`prediction.py:311-316`); API `/regime/latest` chỉ trả `hmm_semantic` và `rf`, không trả combined/transition/highvol trong payload (`prediction.py:100-121`, `347-353`).
- `bar_forecasts` là model HGBT dự đoán nến kế tiếp với `probability_up`; docstring ghi accuracy 0.4967 / AUC 0.5169 và “no exploitable edge”; note trong record cũng ghi AUC ~0.52, chỉ tham khảo (`services/forecast.py:1-18`, `183-196`; `models.py:411-445`).

**Xác suất thắng lệnh BUY/SELL**

- **Chưa có** `p_win`, `win_probability`, expected value, edge hoặc xác suất đạt TP trước SL trong code/DB. `[MISSING]`
- Các số liệu như direction accuracy, false trend rate, outcome forward return là thống kê offline/retrospective, không phải xác suất live cho từng tín hiệu (`ml/history_stats.py`; `ml/outcome.py`; `ml/evaluation.py`).
- Vì vậy EA không được dùng `confidence`/`p_up` như xác suất thắng để tính position size/EV.

### 2.4 Thời điểm phát tín hiệu và tính idempotent

- `/regime/latest` là endpoint GET request-driven, không phải push; nó gọi `regime_latest`, cache 5 giây theo `(symbol, source, latest_ts, hmm_version_id, rf_version_id, engine_params)` (`services/prediction.py:647-687`).
- Khi bar mới chưa có prediction, `compute_latest_regime` chạy inference, lưu một row; nếu đã có thì trả row cũ (`prediction.py:144-167`, `_find_prediction` 75-93).
- `expiry_ts` = `feature_ts + 2*M15`; `data_age_minutes` được trả; nếu stale có thể trả `STALE_DATA`/`stale` (`prediction.py:118`, `134-163`, `331`).
- Worker scheduler chạy mỗi 30 giây và gọi backfill mỗi `backfill_interval_seconds` (mặc định 300 giây), quality, retrain, Telegram (`worker.py:135-185`; `config.py:81-94`). Không có event dispatcher.
- `backfill_predictions` tái tạo prediction cho các bar thiếu, nhưng không phát event; nó chỉ ghi `ModelPrediction` (`prediction.py:389-...`, worker `169-...`).
- `regime/history` trả danh sách prediction theo `limit`, không có cursor/sequence (`routers/regime.py:23-39`).

**Kết luận mục 2:** GMRAI có “nhận diện regime UP/DOWN” ở mức bar, nhưng chưa có “signal event” với lifecycle END/CANCEL/trend_id. Việc EA suy ra event từ snapshot là không đủ tin cậy cho production. `[VERIFIED]` + `[MISSING]`

---

## 3. Khả năng lưu trữ sự kiện hiện tại

| Yêu cầu | Hiện trạng | Dẫn chứng / kết luận |
|---|---|---|
| Event ID duy nhất | `[MISSING]` Không có event table/field. `ModelPrediction.id` là row id, không phải event ID và không ổn định qua backfill/regenerate | `models.py:188-210`; `services/prediction.py:389-...` |
| Sequence ID tăng dần | `[MISSING]` Không có sequence/cursor. `ModelPrediction.id` là autoincrement toàn cục nhưng không phải sequence event theo stream | `models.py:197`; `routers/regime.py:23-39` |
| Event history bất biến | `[PARTIAL/MISSING]` `model_predictions` có unique per model/bar nhưng có retention xoá sau 365 ngày; `regime_history_bars/segments` bị xoá và ghi lại khi regenerate | `models.py:188-210`; `services/retention.py:59-...`; `services/history.py:123-124` |
| Event replay | `[MISSING]` Không có API replay event/cursor; `backfill_predictions` là recompute prediction, không replay event; `/regime/history` chỉ list | `services/prediction.py:389-...`; `routers/regime.py:23-39` |
| State snapshot | `[PARTIAL]` `EngineState.snapshot()` trả state/counters/trend_age; lưu trong `components_json.engine_state` của prediction; restore từ prediction trước | `regime_engine.py:157-175`; `prediction.py:233-234`, `318-323`; không có bảng snapshot độc lập |
| Đồng bộ sau restart | `[PARTIAL]` Live restore từ row prediction trước; worker backfill; nhưng không có EA instance/cursor/ack; retention/gap có thể làm mất state | `prediction.py:229-234`, `389-...`; `worker.py:169-...`; `retention.py:59-...` |

**Điểm gần giống event nhất trong hệ thống hiện tại**

- `TelegramMessage.dedupe_key` unique, dedupe theo `signal:{symbol}:{bar_ts}:{signal}`; đây là log gửi notification, không phải event API/EA delivery. `[VERIFIED]` — `models.py:448-480`, `services/telegram.py:292-...`.
- `BarForecast` unique `(symbol,timeframe,ts)`, immutable cho forecast nến kế tiếp; không phải regime event và không có trend lifecycle. `[VERIFIED]` — `models.py:411-445`, `services/forecast.py:121-...`.
- `SystemLog` ghi log thay đổi registry/admin; không phải audit event EA, không có request_id/sequence. `[VERIFIED]` — `models.py:271-280`, `services/registry.py:44-52`.

**Kết luận mục 3:** chưa có event store đáp ứng EA. Cần bảng event append-only + sequence + cursor + snapshot độc lập. `[MISSING]` + `[PROPOSED]`

---

## 4. Kiến trúc API đề xuất

### 4.1 Nguyên tắc

1. **GMRAI là signal provider, EA là execution client.** GMRAI không giữ mật khẩu broker, không gửi lệnh; EA gửi lệnh tới MT5 và báo kết quả về GMRAI. `[PROPOSED]`
2. **Event-sourced, append-only.** Mỗi thay đổi regime/trend là một event bất biến; sửa sai bằng event mới (supersede/cancel), không UPDATE event cũ. `[PROPOSED]`
3. **At-least-once delivery + idempotent consumer.** EA dedupe bằng `event_id`; execution feedback idempotent bằng `Idempotency-Key`/`client_order_id`. `[PROPOSED]`
4. **REST + long-poll trước, SSE/WebSocket sau.** MQL5 `WebRequest` hỗ trợ HTTP request/response, không phù hợp WebSocket; long-poll 20-25 giây là lựa chọn thực tế. `[PROPOSED]`
5. **Không phá vỡ API hiện tại.** `/regime/latest` và `/regime/history` vẫn cho dashboard/nghiên cứu; namespace mới `/api/v1/ea/*` cho EA. `[PROPOSED]`

### 4.2 Thành phần mới

| Thành phần | Trách nhiệm | Trạng thái |
|---|---|---|
| Event Publisher | So sánh prediction/engine state với trend state, sinh `UP/DOWN/END_*/CANCEL_*`, gán `trend_id`, `event_id`, `sequence_id`; ghi event + trend state + outbox trong một transaction | `[PROPOSED]` |
| Trend State Store | Bảng `trend_states`: một active trend/stream; state_version; start/end event | `[PROPOSED]` |
| Event API | `/ea/events` cursor + long-poll; `/ea/state`; `/ea/snapshot` | `[PROPOSED]` |
| Execution Feedback API | EA báo OPEN/CLOSE/PARTIAL/REJECT/ERROR; lưu order/execution history | `[PROPOSED]` |
| EA Heartbeat / Health | EA liveness, last_sequence/state_version, open positions summary; health cho EA | `[PROPOSED]` |
| EA Auth | API key/credential scope `events:read`, `state:read`, `execution:write`, `heartbeat:write`; TLS, IP allowlist, rotation | `[PROPOSED]` |
| Audit | `api_audit_logs`, request_id, actor_type, event/order | `[PROPOSED]` |

### 4.3 Định nghĩa event lifecycle đề xuất

| Event | Khi phát | Ý nghĩa cho EA | Trend ID |
|---|---|---|---|
| `UP` | Engine xác nhận trend tăng mới (entry/override) | Mở phép LONG mới nếu `tradeable=true` | Tạo mới |
| `DOWN` | Engine xác nhận trend giảm mới | Mở SHORT mới | Tạo mới |
| `END_UP` | Trend tăng kết thúc (engine rời TREND_UP về base, hoặc bị thay bằng DOWN) | Đóng LONG; không mở LONG mới | Giữ nguyên trend cũ |
| `END_DOWN` | Trend giảm kết thúc | Đóng SHORT | Giữ nguyên |
| `CANCEL_UP` | Signal LONG bị huỷ trước khi EA thực thi/trước khi trend được xác nhận đủ; hoặc dữ liệu/model không còn hợp lệ | Không mở LONG; nếu đã mở ngoài ý muốn thì đóng | Cùng trend bị huỷ |
| `CANCEL_DOWN` | Tương tự cho SHORT | Không mở SHORT | Cùng trend |
| `EARLY_UP/DOWN` (tuỳ chọn, **không** tradeable) | Early advisory | Chỉ hiển thị/telemetry, không vào lệnh | Không tạo trend tradeable |

**Quy tắc thứ tự:** nếu một bar vừa kết thúc trend cũ vừa bắt đầu trend ngược, publisher phải phát `END_UP` trước `DOWN` (hoặc `END_DOWN` trước `UP`) trong cùng transaction, sequence tăng dần; EA xử lý theo thứ tự sequence. Nếu EA bỏ lỡ cả hai, state snapshot phải trả trend hiện tại và EA phải reconcile.

**Quy tắc `CANCEL`:** cần chốt với product. Đề xuất: `CANCEL_*` chỉ dùng khi event entry đã phát nhưng trend chưa được xác nhận đủ/không còn hợp lệ trước khi EA thực thi; nếu EA đã mở lệnh, `CANCEL` yêu cầu EA đóng với `client_order_id` idempotent. `END_*` dùng cho trend đã hoàn tất tự nhiên, không dùng lẫn với `CANCEL_*`.

### 4.4 Sequence/state version

- `event_id`: UUIDv7/ULID, unique toàn hệ thống.
- `sequence_id`: BIGINT tăng dần **theo stream** (symbol+timeframe), cấp phát trong transaction bằng bảng `event_streams.next_sequence` có row lock; không dùng `ModelPrediction.id` vì nó là autoincrement toàn cục và có thể lẫn backfill/retention.
- `state_version`: BIGINT tăng mỗi lần trend state/active trend thay đổi; snapshot và event đều mang state_version để client phát hiện lệch.
- `trend_id`: UUID tạo khi `UP/DOWN`; giữ nguyên qua `END/CANCEL`; không tái sử dụng.
- `previous_event_id`, `supersedes_event_id` để nối/lịch sử.

### 4.5 Auth đề xuất

- Không dùng JWT admin/analyst trong EA.
- Credential riêng cho EA, gắn `ea_instance_id`; scope tối thiểu; hash lưu DB; rotate/revoke; hết hạn; IP allowlist; TLS bắt buộc.
- Header đề xuất: `X-EA-Key: <opaque-token>`; optional `X-GMRAI-Timestamp` + `X-GMRAI-Signature` (HMAC) để chống replay; body hash; request_id.
- API key hiện tại chỉ có `role` dạng string và `ingest_identity` không kiểm tra role/scope; cần mở rộng hoặc bảng credential mới. `[VERIFIED]` — `models.py:33-42`, `deps.py:43-61`, `admin.py:307-324`.
- Rate limit: theo EA instance + IP; `429` + `Retry-After`; tách khỏi window JWT.

### 4.6 Health đề xuất

- `/api/v1/ea/health` trả: `api`, `database`, `engine`, `worker`, `last_bar_age_seconds`, `last_event_age_seconds`, `latest_sequence`, `latest_state_version`, `active_model_version`, `active_trend`, `degraded_reasons`, `server_time`.
- Trả 503 nếu DB/engine unavailable; 200 + `degraded=true` nếu dữ liệu stale/model degraded (để EA còn lấy state và đóng/no new entries).
- Health hiện tại chỉ kiểm tra API/DB/worker (`main.py:110-159`) và không kiểm tra engine/model/data/event lag. `[VERIFIED]`

---

## 5. API Contract chi tiết

**Base:** `/api/v1/ea`  
**Schema version:** `1.0` (mọi response có `schema_version`).  
**Auth:** `X-EA-Key` + optional HMAC/TLS; scope theo endpoint. Không dùng admin JWT.  
**Content type:** `application/json`; timestamps ISO-8601 UTC.

### 5.1 Endpoint summary

| Method | Path | Scope | Mục đích |
|---|---|---|---|
| GET | `/events` | `events:read` | Lấy event theo cursor; hỗ trợ long-poll |
| GET | `/events/{event_id}` | `events:read` | Lấy một event để debug/dedupe |
| GET | `/state` | `state:read` | Snapshot state hiện tại của stream |
| GET | `/snapshot` | `state:read` | State + N event gần nhất để resync |
| POST | `/executions` | `execution:write` | EA báo execution/fill/reject |
| POST | `/heartbeats` | `heartbeat:write` | EA heartbeat + vị thế hiện tại |
| POST | `/acks` | `events:read` | Ack cursor/consumed event (tuỳ chọn) |
| GET | `/health` | `health:read` | Health chuyên cho EA |
| GET | `/config` | `state:read` | Symbol/timeframe/session/model version (tuỳ chọn) |

### 5.2 GET `/events`

**Query**

| Tên | Kiểu | Mặc định | Ghi chú |
|---|---|---|---|
| `symbol` | string | `XAUUSD` | |
| `timeframe` | string | `M15` | |
| `after_sequence` | integer | 0 | Chỉ trả event có sequence > giá trị này |
| `limit` | integer | 100 | 1–500 |
| `wait_seconds` | integer | 0 | 0–25; long-poll nếu >0 |
| `include_state` | boolean | false | Kèm state snapshot |

**Response 200 (có event)**

```json
{
  "schema_version": "1.0",
  "stream": {"symbol": "XAUUSD", "timeframe": "M15"},
  "events": [
    {
      "event_id": "0192f3a0-7a4e-7b2a-9e31-0d3d1f4c8a01",
      "sequence_id": 1842,
      "schema_version": "1.0",
      "symbol": "XAUUSD",
      "timeframe": "M15",
      "event_type": "UP",
      "trend_id": "0192f3a0-6f1e-7c59-9a10-3c5e9a2b7d44",
      "direction": "LONG",
      "bar_ts": "2026-11-17T08:00:00Z",
      "bar_close_ts": "2026-11-17T08:15:00Z",
      "generated_at": "2026-11-17T08:15:03.120Z",
      "valid_until": "2026-11-17T08:45:00Z",
      "model_version_id": 9,
      "feature_version": "v1",
      "state_version": 91,
      "confidence": 0.63,
      "probabilities": {
        "p_up": 0.63,
        "p_down": 0.12,
        "p_side": 0.21,
        "p_trans": 0.02,
        "p_highvol": 0.02,
        "agreement": 0.81
      },
      "tradeable": true,
      "reason_codes": ["CONFIRM_1", "RF_HMM_AGREE", "STATE_DETECTOR_OVERRIDE"],
      "previous_event_id": "0192f3a0-5f11-7d0e-8b21-a1a1a1a1a1a1",
      "supersedes_event_id": null,
      "payload_hash": "sha256:..."
    }
  ],
  "next_sequence": 1842,
  "latest_sequence": 1847,
  "has_more": true,
  "snapshot_required": false,
  "server_time": "2026-11-17T08:15:03.120Z"
}
```

**Response 200 (long-poll không có event mới)**

```json
{
  "schema_version": "1.0",
  "stream": {"symbol": "XAUUSD", "timeframe": "M15"},
  "events": [],
  "next_sequence": 1842,
  "latest_sequence": 1842,
  "has_more": false,
  "snapshot_required": false,
  "server_time": "2026-11-17T08:15:28Z"
}
```

**Response 410 khi cursor quá cũ**

```json
{
  "error": {
    "code": "EVENT_CURSOR_EXPIRED",
    "message": "Cursor is older than the retained event window",
    "request_id": "req_01J...",
    "details": {
      "oldest_available_sequence": 3021,
      "latest_sequence": 18420,
      "snapshot_url": "/api/v1/ea/snapshot?symbol=XAUUSD&timeframe=M15"
    }
  }
}
```

**Quy tắc**

- Event được trả theo `sequence_id` tăng dần.
- `next_sequence` = sequence cuối cùng đã trả (hoặc cursor hiện tại nếu không có event).
- `snapshot_required=true` khi EA nên gọi `/snapshot` trước khi xử lý event.
- Long-poll không giữ kết nối quá 25s để tránh timeout MQL5/nginx; nếu hết hạn trả mảng rỗng, không trả lỗi.
- `limit` chunk; `has_more=true` nghĩa còn event trong retention window.
- Event `UP/DOWN` chỉ là **signal**, không phải lệnh; EA phải kiểm tra `tradeable`, `expiry`, `state`.

### 5.3 GET `/state`

**Response 200**

```json
{
  "schema_version": "1.0",
  "stream": {"symbol": "XAUUSD", "timeframe": "M15"},
  "state_version": 91,
  "last_sequence": 1847,
  "last_event_id": "0192f3a0-7a4e-7b2a-9e31-0d3d1f4c8a01",
  "trend_id": "0192f3a0-6f1e-7c59-9a10-3c5e9a2b7d44",
  "trend_status": "ACTIVE",
  "direction": "LONG",
  "regime": "TREND_UP",
  "permission": "BUY_ONLY",
  "tradeable": true,
  "confidence": 0.63,
  "probabilities": {
    "p_up": 0.63, "p_down": 0.12, "p_side": 0.21,
    "p_trans": 0.02, "p_highvol": 0.02, "agreement": 0.81
  },
  "model_version_id": 9,
  "feature_version": "v1",
  "bar_ts": "2026-11-17T08:00:00Z",
  "bar_close_ts": "2026-11-17T08:15:00Z",
  "data_timestamp": "2026-11-17T08:15:00Z",
  "data_age_seconds": 24,
  "stale": false,
  "valid_until": "2026-11-17T08:45:00Z",
  "reason_codes": ["CONFIRM_1", "RF_HMM_AGREE"],
  "engine": {
    "state": "TREND_UP",
    "trend_age": 8,
    "up_confirm": 0,
    "down_confirm": 0,
    "exit_count": 0
  },
  "server_time": "2026-11-17T08:15:24Z"
}
```

**Quy tắc**

- State API là **snapshot chuẩn** để EA resync khi bỏ lỡ event hoặc restart.
- Nếu dữ liệu stale/inference fail: vẫn nên trả 200 với `stale=true`, `tradeable=false`, `degraded_reasons=["STALE_DATA"]`; EA không mở lệnh mới, xử lý đóng theo policy.
- Nếu DB/engine không thể xác định state: 503 `ENGINE_UNAVAILABLE`.
- `trend_status`: `NONE|ACTIVE|ENDED|CANCELLED`.

### 5.4 GET `/snapshot`

Trả state hiện tại + `events` gần nhất (mặc định 50, tối đa 200) + `snapshot_version`. Dùng khi 410/cursor expired hoặc EA restart.

```json
{
  "schema_version": "1.0",
  "state": { "...": "cùng schema /state" },
  "events": [ "… tối đa 200 event gần nhất …" ],
  "snapshot_version": 91,
  "server_time": "2026-11-17T08:15:24Z"
}
```

### 5.5 POST `/executions`

**Headers bắt buộc**

| Header | Mô tả |
|---|---|
| `Idempotency-Key` | UUID/opaque, unique theo `ea_instance_id` |
| `X-EA-Key` | Credential của EA instance |

**Body**

```json
{
  "schema_version": "1.0",
  "ea_instance_id": "ea_ftmo_demo_01",
  "event_id": "0192f3a0-7a4e-7b2a-9e31-0d3d1f4c8a01",
  "trend_id": "0192f3a0-6f1e-7c59-9a10-3c5e9a2b7d44",
  "client_order_id": "ea_ftmo_demo_01:0192f3a0:open:1",
  "action": "OPEN",
  "symbol": "XAUUSD",
  "side": "BUY",
  "order_type": "MARKET",
  "requested_volume": 0.10,
  "status": "FILLED",
  "broker_order_id": "123456789",
  "broker_ticket": "987654321",
  "fill_price": 4123.45,
  "filled_volume": 0.10,
  "slippage_points": 3,
  "error_code": null,
  "error_message": null,
  "occurred_at": "2026-11-17T08:15:05.420Z",
  "metadata": {"magic": 20261117, "comment": "gmrai"}
}
```

**Response 201**

```json
{
  "schema_version": "1.0",
  "execution_id": "0192f3b1-2c03-7a01-9e12-55aa66bb77cc",
  "status": "RECORDED",
  "duplicate": false,
  "server_time": "2026-11-17T08:15:05.620Z"
}
```

**Quy tắc**

- `client_order_id` unique trong `ea_instance_id`; `Idempotency-Key` unique; request trùng key + body hash trả lại response gốc (`duplicate=true`), request trùng key khác body → 409 `IDEMPOTENCY_CONFLICT`.
- `event_id`/`trend_id` phải tồn tại; nếu không → 422 `EVENT_NOT_FOUND`.
- Không cho feedback đóng một order đã đóng với cùng `client_order_id` nếu payload khác; append execution event mới nếu là correction.
- GMRAI **không** gửi lệnh; endpoint này chỉ ghi nhận feedback.

### 5.6 POST `/heartbeats`

```json
{
  "schema_version": "1.0",
  "ea_instance_id": "ea_ftmo_demo_01",
  "status": "RUNNING",
  "version": "1.0.0",
  "last_sequence": 1847,
  "last_event_id": "0192f3a0-7a4e-7b2a-9e31-0d3d1f4c8a01",
  "last_state_version": 91,
  "open_positions": [
    {"trend_id": "0192f3a0-...", "side": "BUY", "volume": 0.10, "ticket": "987654321", "unrealized_pnl": 12.4}
  ],
  "latency_ms": 182,
  "occurred_at": "2026-11-17T08:16:00Z"
}
```

Response 200 `{"status":"ok","server_time":"..."}`. Heartbeat upsert `ea_instances`, insert `ea_heartbeats` (append-only), cập nhật `ea_cursors.last_ack_sequence` nếu có.

### 5.7 POST `/acks` (tuỳ chọn)

`{ea_instance_id, stream, event_id, sequence_id, status:"PROCESSED|SKIPPED|FAILED"}`; unique `(ea_instance_id,event_id)`; dùng để theo dõi delivery/consumer lag. Nếu không dùng ack, heartbeat `last_sequence` là đủ cho MVP.

### 5.8 GET `/health`

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "api": "ok",
  "database": "ok",
  "engine": "running",
  "worker": "running",
  "last_bar_age_seconds": 12,
  "last_event_age_seconds": 12,
  "latest_sequence": 1847,
  "latest_state_version": 91,
  "active_model_version_id": 9,
  "active_trend": {"trend_id": "...", "direction": "LONG"},
  "degraded": false,
  "degraded_reasons": [],
  "server_time": "2026-11-17T08:15:24Z"
}
```

HTTP 503 nếu DB/engine unavailable; 200 + `degraded=true` nếu stale/model degraded.

### 5.9 Lỗi chuẩn

```json
{
  "error": {
    "code": "EVENT_CURSOR_EXPIRED",
    "message": "Cursor is older than retained window",
    "request_id": "req_01J...",
    "timestamp": "2026-11-17T08:15:24Z",
    "details": {}
  }
}
```

| HTTP | Code | Khi nào |
|---|---|---|
| 400 | `BAD_REQUEST` | Query/body không hợp lệ |
| 401 | `AUTH_MISSING` / `AUTH_INVALID` | Thiếu/sai EA key |
| 403 | `FORBIDDEN_SCOPE` / `EA_DISABLED` | Scope thiếu/instance bị tắt |
| 404 | `EVENT_NOT_FOUND` / `ORDER_NOT_FOUND` | Event/order không tồn tại |
| 409 | `IDEMPOTENCY_CONFLICT` | Cùng key khác payload |
| 409 | `STATE_VERSION_CONFLICT` | State version stale khi update (nếu cho phép) |
| 410 | `EVENT_CURSOR_EXPIRED` | Cursor ngoài retention; kèm snapshot URL |
| 422 | `VALIDATION_ERROR` / `EVENT_NOT_FOUND` | Field sai, event không khớp |
| 429 | `RATE_LIMITED` | Vượt rate limit; có `Retry-After` |
| 500 | `INTERNAL_ERROR` | Lỗi không xác định; không lộ stack |
| 503 | `ENGINE_UNAVAILABLE` / `DB_UNAVAILABLE` | Engine/DB down; retry sau |

**Ghi chú so với hiện tại:** API hiện tại trả `{"detail": "..."}` (`docs/API_CONTRACT.md:130-135`), không có envelope/request_id; `_compute_regime_payload` biến lỗi inference thành payload `UNKNOWN` HTTP 200 (`prediction.py:608-644`). Với EA, nên giữ `UNKNOWN` cho `/regime/latest` (dashboard) nhưng `/ea/state`/`/ea/events` phải có semantics rõ: 200 + `tradeable=false` hoặc 503, không để EA hiểu nhầm `UNKNOWN` là tín hiệu.

### 5.10 Retry / recovery / idempotency

- GET events/state: retry an toàn, exponential backoff + jitter; 429/503/network; `after_sequence` không đổi.
- POST execution: retry **cùng** `Idempotency-Key`; server trả record gốc; EA không tạo order mới. Sau timeout, EA reconcile broker trước khi retry.
- Long-poll: client timeout > `wait_seconds` (ví dụ 30s), reconnect ngay; không coi timeout là lỗi.
- 410 cursor expired: gọi `/snapshot`, bỏ qua event cũ; EA reconcile vị thế broker với state hiện tại; không replay lệnh cũ.
- Event delivery là at-least-once; EA dedupe theo `event_id`; execution orders dedupe theo `(ea_instance_id, client_order_id)`.
- Server restart: event/state durable trong DB; cache in-memory mất nhưng tái tạo; outbox đảm bảo event không mất; worker retry.
- EA restart: đọc `/state` + `/snapshot`; reconcile open positions/orders với broker; không giả định order đã đóng.

### 5.11 Versioning

- `/api/v1/ea` cố định; `schema_version` trong payload; event immutable.
- Thay đổi additive: thêm field optional; thay đổi semantics phải bump major/schema_version và chạy song song.
- Không đổi ý nghĩa `UP/DOWN/END/CANCEL` sau khi EA đã consume; nếu cần, phát event version mới.

---

## 6. Database Schema đề xuất

> Tất cả bảng dưới đây là `[PROPOSED]`, chưa có trong code. Kiểu ghi theo SQLAlchemy/PostgreSQL; SQLite dev có thể dùng biến thể tương đương.

### 6.1 Bảng mới

#### `event_streams`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `stream_id` | varchar PK | `XAUUSD:M15` |
| `symbol` | varchar | |
| `timeframe` | varchar | |
| `next_sequence` | bigint | Cấp trong transaction; row lock |
| `latest_event_id` | uuid nullable | |
| `latest_state_version` | bigint | |
| `updated_at` | timestamptz | |

Unique `(symbol,timeframe)`.

#### `signal_events`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `event_id` | uuid PK | UUIDv7/ULID |
| `sequence_id` | bigint | Unique theo `stream_id` |
| `schema_version` | varchar | `1.0` |
| `stream_id` | varchar FK → event_streams | |
| `symbol`, `timeframe` | varchar | |
| `event_type` | varchar | `UP|DOWN|END_UP|END_DOWN|CANCEL_UP|CANCEL_DOWN` |
| `trend_id` | uuid FK → trend_states | |
| `direction` | varchar | `LONG|SHORT|NONE` |
| `bar_ts`, `bar_close_ts` | timestamptz | Bar tạo tín hiệu |
| `generated_at`, `valid_until` | timestamptz | |
| `model_version_id` | int FK → model_versions | |
| `feature_version` | varchar | |
| `state_version` | bigint | |
| `confidence` | float | |
| `probabilities_json` | json | p_up/p_down/p_side/p_trans/p_highvol/agreement |
| `tradeable` | bool | `false` cho EARLY/UNKNOWN |
| `reason_codes_json` | json | |
| `previous_event_id`, `supersedes_event_id` | uuid nullable | |
| `source_prediction_id` | int nullable | Link `model_predictions.id` |
| `payload_hash` | varchar | Integrity |
| `created_at` | timestamptz | |

Ràng buộc:
- Unique `(stream_id, sequence_id)`.
- Unique `event_id`.
- Index `(stream_id, sequence_id)`.
- Check `event_type`/`direction`/`probabilities_json` shape ở application layer.
- Append-only: không UPDATE/DELETE; correction dùng event mới.

#### `trend_states`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `trend_id` | uuid PK | |
| `stream_id` | varchar FK | |
| `direction` | varchar | LONG/SHORT |
| `status` | varchar | ACTIVE/ENDED/CANCELLED |
| `start_event_id` | uuid FK | `UP/DOWN` |
| `end_event_id` | uuid nullable | `END_*`/`CANCEL_*` |
| `started_at`, `ended_at` | timestamptz | |
| `state_version` | bigint | Tăng mỗi transition |
| `model_version_id` | int FK | Model tạo trend |
| `version` | int | Optimistic lock |
| `updated_at` | timestamptz | |

Ràng buộc:
- Partial unique index `UNIQUE(stream_id) WHERE status='ACTIVE'` — một active trend/stream.
- `status=ACTIVE` ⇒ `ended_at IS NULL`, `end_event_id IS NULL`.

#### `event_outbox`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `outbox_id` | bigint PK | |
| `event_id` | uuid unique FK | |
| `status` | varchar | PENDING/SENT/FAILED |
| `attempts` | int | |
| `next_attempt_at` | timestamptz | |
| `last_error` | text nullable | |
| `created_at`, `published_at` | timestamptz | |

Dùng nếu event publisher/notification tách khỏi transaction; pull API có thể đọc trực tiếp `signal_events`, outbox dùng cho webhook/push sau này.

#### `state_snapshots`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `snapshot_id` | bigint PK | |
| `stream_id` | varchar FK | |
| `state_version` | bigint | |
| `last_sequence` | bigint | |
| `snapshot_json` | json | trend/engine state, không chứa secret |
| `created_at` | timestamptz | |

Unique `(stream_id,state_version)`; index `(stream_id,created_at)`.

#### `ea_instances`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `ea_instance_id` | varchar PK | UUID/name |
| `name` | varchar | |
| `account_login` | varchar | Không lưu password |
| `broker_server` | varchar | |
| `symbol`, `timeframe` | varchar | |
| `api_key_id` | int FK → api_keys | |
| `status` | varchar | ACTIVE/DISABLED/REVOKED |
| `version` | varchar | EA version |
| `last_heartbeat_at` | timestamptz | |
| `last_sequence` | bigint | |
| `last_event_id` | uuid | |
| `last_state_version` | bigint | |
| `metadata_json` | json | |
| `created_at`, `updated_at` | timestamptz | |

#### `ea_cursors`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `ea_instance_id` | varchar FK | |
| `stream_id` | varchar FK | |
| `last_ack_sequence` | bigint | |
| `last_ack_event_id` | uuid | |
| `last_ack_state_version` | bigint | |
| `updated_at` | timestamptz | |

PK `(ea_instance_id, stream_id)`; unique.

#### `execution_orders`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `order_id` | uuid PK | |
| `client_order_id` | varchar | Unique theo EA instance |
| `ea_instance_id` | varchar FK | |
| `event_id` | uuid FK | Signal event |
| `trend_id` | uuid FK | |
| `symbol`, `side`, `order_type` | varchar | |
| `status` | varchar | PENDING/OPEN/PARTIAL/CLOSED/REJECTED/CANCELLED |
| `requested_volume`, `filled_volume` | numeric | |
| `avg_fill_price`, `close_price` | numeric | |
| `broker_order_id`, `broker_ticket` | varchar nullable | |
| `opened_at`, `closed_at` | timestamptz | |
| `pnl`, `commission`, `swap`, `slippage_points` | numeric | |
| `idempotency_key` | varchar | Unique theo EA |
| `metadata_json` | json | |
| `created_at`, `updated_at` | timestamptz | |

Unique `(ea_instance_id, client_order_id)`; index `(event_id)`, `(trend_id)`, `(status)`.

#### `execution_events` (execution history, append-only)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `execution_event_id` | uuid PK | |
| `order_id` | uuid FK | |
| `ea_instance_id` | varchar FK | |
| `event_id` | uuid FK | Signal event |
| `type` | varchar | ACK/OPEN/FILL/PARTIAL/CLOSE/REJECT/ERROR |
| `status` | varchar | |
| `broker_payload_json` | json | Raw broker response (đã lọc secret) |
| `price`, `volume` | numeric | |
| `broker_code` | varchar nullable | |
| `occurred_at`, `received_at` | timestamptz | |
| `idempotency_key` | varchar | Unique |
| `created_at` | timestamptz | |

Index `(order_id,occurred_at)`, `(ea_instance_id,received_at)`.

#### `ea_heartbeats`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `heartbeat_id` | bigint PK | |
| `ea_instance_id` | varchar FK | |
| `status` | varchar | RUNNING/DEGRADED/STOPPED |
| `last_sequence`, `last_state_version` | bigint | |
| `open_positions_json` | json | Summary, không credential |
| `latency_ms` | int | |
| `version` | varchar | |
| `ip` | varchar | |
| `received_at` | timestamptz | |

Index `(ea_instance_id,received_at)`; retention.

#### `api_audit_logs`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `audit_id` | bigint PK | |
| `actor_type` | varchar | USER/EA/COLLECTOR/SYSTEM |
| `actor_id` | varchar | |
| `action` | varchar | |
| `method`, `path` | varchar | |
| `status_code` | int | |
| `request_id` | varchar | |
| `event_id`, `order_id` | uuid nullable | |
| `ip` | varchar | |
| `request_hash` | varchar | |
| `created_at` | timestamptz | |

Append-only; index `(actor_type,actor_id,created_at)`.

### 6.2 Mở rộng bảng hiện có

- `api_keys`: thêm `scopes_json`, `expires_at`, `bound_ea_instance_id` (hoặc tạo `ea_credentials` riêng). Hiện chỉ có `role` string và `ingest_identity` không enforce scope (`models.py:33-42`, `deps.py:43-61`).
- `model_versions`: giữ nguyên; event/order tham chiếu `id`. Nếu cần nhóm HMM/RF theo training pair, thêm `pair_id` hoặc tiếp tục dùng `model_id` (đang được `get_active_approved_pair` dùng, `services/registry.py:73-97`).
- `model_predictions`: giữ nguyên làm nguồn per-bar; event publisher tham chiếu `source_prediction_id`. Không nên biến `model_predictions` thành event store vì retention/backfill/regenerate.

### 6.3 Quan hệ

```
model_versions 1 ─── N signal_events
trend_states 1 ─── N signal_events        (start / end / cancel cùng trend_id)
signal_events 1 ─── 1 event_outbox
signal_events 1 ─── N execution_orders
trend_states 1 ─── N execution_orders
ea_instances 1 ─── N execution_orders
execution_orders 1 ─── N execution_events
ea_instances 1 ─── N ea_heartbeats
ea_instances 1 ─── N ea_cursors
ea_cursors N ─── 1 event_streams
state_snapshots N ─── 1 event_streams
api_audit_logs N ─── optional signal_events/execution_orders
```

### 6.4 Nhất quán dữ liệu

1. **Transaction sinh event:** trong một transaction:
   - Lock `event_streams` row (`SELECT ... FOR UPDATE`).
   - Tăng `next_sequence`.
   - Chèn `signal_events`.
   - Cập nhật/đóng `trend_states` và `latest_state_version`.
   - Chèn `event_outbox` nếu dùng.
   - Commit. Nếu rollback, sequence không tăng (hoặc chấp nhận gap có kiểm soát); event không tồn tại.
2. **Append-only:** không UPDATE/DELETE `signal_events`/`execution_events`; correction bằng event mới với `supersedes_event_id`; audit.
3. **Idempotency:** unique `signal_events.event_id`; unique `(ea_instance_id,client_order_id)`; unique `(ea_instance_id,idempotency_key)`; unique `(ea_instance_id,event_id)` cho ack.
4. **One active trend:** partial unique index `trend_states(stream_id) WHERE status='ACTIVE'`; transition ACTIVE→ENDED/CANCELLED chỉ một lần.
5. **FK:** bật foreign key; PostgreSQL mặc định; SQLite cần `PRAGMA foreign_keys=ON` nếu dùng dev.
6. **Retention:** event giữ tối thiểu 90 ngày; snapshot 1 năm; audit 1 năm; EA cursor cũ hơn retention → 410 snapshot. Không xoá `trend_states`/event đang active.
7. **Clock:** tất cả UTC; `server_time` trong response; EA dùng `occurred_at` + `received_at`, không dùng giờ local làm khóa.
8. **Backup/migration:** migration Alembic mới; backup trước migration; không sửa bảng cũ trừ additive columns.

### 6.5 Ghi chú schema hiện tại

- Code `MarketCandle` unique gồm `source` (`models.py:45-52`), nhưng docs `DATABASE_SCHEMA.md:40` vẫn ghi unique `(symbol,timeframe,ts)` — lệch tài liệu. DB dev thực tế có `UNIQUE(symbol,timeframe,source,ts)` (SQLite DDL đã kiểm tra). Cần sửa docs khi triển khai event layer. `[VERIFIED]`
- `ModelPrediction` unique per `(model_version_id,symbol,timeframe,ts)` (`models.py:190-195`) là idempotency tốt cho per-bar, nhưng không đủ event ordering/trend lifecycle. `[VERIFIED]`

---

## 7. Phân tích tình huống lỗi

> Cột “Hiện tại” chỉ ra mức hỗ trợ trong code hiện tại; các cột “Đề xuất” là thiết kế mới.

| Tình huống | Hiện tại | GMRAI đề xuất | EA đề xuất |
|---|---|---|---|
| EA mất kết nối | Không có heartbeat/event API; EA phải poll snapshot và tự diff | Event/state durable; heartbeat timeout alert; cursor/ack; snapshot | Retry backoff; reconnect với `after_sequence`; nếu 410 gọi snapshot; reconcile broker; không mở lệnh mới khi state stale |
| API server restart | DB giữ prediction/history; cache 5s mất; worker in-process jobs có thể mất (`worker.py:17-...`, `main.py:74-80`) | Event/outbox/state trong DB; publisher tái tạo; health/readiness; idempotent | Retry GET; không coi timeout là mất event; dedupe event_id; đọc state/snapshot |
| GMRAI Engine dừng | `/regime/latest` có thể trả snapshot cũ/stale; health chỉ API/DB/worker (`main.py:110-159`) | `/ea/health` báo engine/last event age/last bar age; `tradeable=false`; không phát event mới | Không mở lệnh mới sau `valid_until`/stale; giữ SL/TP; đóng theo policy; alert/kill switch |
| EA nhận event trùng | Không có event delivery; prediction idempotent per bar | `event_id` unique; cursor; ack; response duplicate | Dedupe `event_id`/sequence; `client_order_id` unique; không gửi order lần 2 |
| EA bỏ lỡ nhiều event | `/regime/history` chỉ limit, không cursor/410 | `after_sequence`, `has_more`, `410 EVENT_CURSOR_EXPIRED`, snapshot | Detect gap; gọi events theo chunk; nếu cursor expired → snapshot; reconcile; không replay lệnh cũ |
| Broker từ chối đóng lệnh | Không có execution feedback/order table | Ghi `REJECTED`/`CLOSE_REJECTED`; audit; alert; giữ order OPEN; không giả định đóng | Retry idempotent; reconcile ticket; có thể đóng tay; kill switch; báo lỗi |
| EA restart khi đang đóng lệnh | Không có EA state/order persistence | `execution_orders` + `execution_events` + snapshot; trạng thái PENDING/CLOSE_PENDING | Đọc state/snapshot; query broker orders/positions; không gửi trùng; hoàn tất close hoặc reconcile |
| Hai event ngược chiều liên tiếp | Chỉ có regime đổi; không event/ordering | Phát `END_UP` rồi `DOWN` (hoặc ngược) cùng transaction, sequence tăng dần; state_version | Xử lý theo sequence; đóng vị thế cũ trước mở mới; nếu gap → snapshot; không mở 2 chiều ngoài policy |
| Dữ liệu stale / market closed | `/regime/latest` có `data_age`, `stale`, `STALE_DATA`, `market_closed` (`prediction.py:134-163`) | `/ea/state` trả stale + `tradeable=false`; không tạo event mới | Không mở mới; giữ/đóng theo policy; không dùng event cũ |
| Model đổi giữa trend | Không có event model change; prediction model_version thay đổi | Event `CANCEL/END` hoặc trường `model_version_id`; policy đóng/reconcile | Từ chối event model version không cho phép; đóng trend cũ nếu model mismatch; snapshot |
| Clock skew / DST | Hệ thống dùng UTC; config Telegram +7 (`config.py:55-61`) | UTC trong mọi payload; `server_time`; không dùng giờ local làm khóa | Đồng bộ NTP; dùng `bar_ts`/`valid_until` UTC; không so sánh giờ local |
| API quá tải / DB lock | SQLite dev + worker thread; chưa có backpressure cho EA | Rate limit theo EA; 429 Retry-After; Postgres production; index | Backoff; không spam; giữ state; alert |
| Auth sai/hết hạn | EA chưa có credential riêng; JWT user/ingest key | 401/403/429; key rotate/revoke; audit | Không giao dịch; log; alert; dừng EA an toàn |
| Partial fill / slippage | Không có execution model | `execution_events` ghi PARTIAL/FILL/slippage; order status | Báo feedback; reconcile volume; không giả định fill đủ |
| Nhiều EA cùng stream | Không có instance/cursor | Mỗi EA cursor/ack riêng; event dùng chung; không mark global | Mỗi EA dedupe/order id riêng; tránh đánh dấu event đã đọc toàn hệ thống |

**Chi tiết hai event ngược chiều:** nếu `TREND_UP` đang ACTIVE và engine chuyển sang `TREND_DOWN`, publisher phải:
1. tạo `END_UP` với cùng `trend_id`, `state_version+1`;
2. tạo `DOWN` với `trend_id` mới, `state_version+2`;
3. ghi cả hai trong cùng transaction, sequence liên tiếp;
4. EA đóng LONG trước, sau đó mở SHORT; nếu EA chỉ thấy `DOWN` do gap, snapshot trả state hiện tại và EA phải reconcile vị thế cũ trước.

---

## 8. Sơ đồ luồng dữ liệu

### 8.1 Hiện tại

```
MT5 Terminal (Windows)
   │  nến đã đóng + tick
   ▼
Collector (Python MetaTrader5)
   │  HTTPS POST /ingest/candles (X-API-Key)
   ▼
FastAPI Ingestion ──► market_candles / data_sync_logs
   │
   ▼
Feature builder (M15+H1+M5, causal)
   │
   ├── HMM filtered posterior ─┐
   └── RF 3-class probabilities ┴──► Regime Engine (hysteresis/confirm/gates)
                                           │
                                           ▼
                                  ModelPrediction (per bar)
                                           │
                    ┌──────────────────────┼─────────────────────┐
                    ▼                      ▼                     ▼
             /regime/latest          /regime/history        Telegram notify
             (poll snapshot)         (research list)        (dedupe log)
                    │
                    ▼
              Dashboard / client tự diff snapshot
```

### 8.2 Đề xuất cho EA

```
EngineState.step (existing)
   │  regime/confidence/state snapshot
   ▼
Event Publisher [NEW]
   │  so sánh trend state; tạo UP/DOWN/END_*/CANCEL_*
   │  transaction: event_streams + signal_events + trend_states + event_outbox
   ▼
PostgreSQL [NEW tables]
   │
   ├── GET /api/v1/ea/events?after_sequence  ◄── MT5 EA (long-poll)
   ├── GET /api/v1/ea/state                  ◄── MT5 EA
   ├── GET /api/v1/ea/snapshot               ◄── MT5 EA khi 410/restart
   ├── POST /api/v1/ea/heartbeats            ◄── EA
   ├── POST /api/v1/ea/executions            ◄── EA (fill/reject/close)
   └── GET /api/v1/ea/health                 ◄── EA/monitoring
                    │
                    ▼
             MT5 broker (EA gửi lệnh; GMRAI không giữ broker credential)
```

---

## 9. Kế hoạch triển khai theo giai đoạn

> Không code trong giai đoạn audit này. Các phase dưới đây là roadmap đề xuất.

| Phase | Mục tiêu | Deliverable | Exit criteria |
|---|---|---|---|
| 0. Audit (hiện tại) | Xác minh hiện trạng, chốt gap | Báo cáo này | Stakeholder đọc/duyệt; không thay đổi code |
| 1. Contract freeze | Chốt semantics UP/DOWN/END/CANCEL, trend_id, sequence, auth, error, retention | API spec + DB migration design + state machine diagram | Product/risk/EA dev ký; không còn ambiguity CANCEL vs END |
| 2. Event shadow | Sinh event song song prediction, chưa cho EA giao dịch | `signal_events`, `trend_states`, `event_streams`, `state_snapshots`, publisher/outbox chạy shadow | So sánh event với diff prediction 100% bar; không mất/không trùng; tests event/sequence |
| 3. Read-only EA | EA chỉ đọc event/state/snapshot, log; chưa đặt lệnh | `/ea/events`, `/ea/state`, `/ea/snapshot`, `/ea/health`, EA credential scope | EA chạy shadow 2–4 tuần; 0 missed transition; latency/health đạt |
| 4. Demo execution | EA đặt lệnh demo, gửi execution feedback/heartbeat | `/ea/executions`, orders/execution tables, audit, dashboard | Demo 0.01 lot 4–8 tuần; không duplicate order; reconcile đúng; risk limits |
| 5. Limited live | Chạy vốn nhỏ/FTMO demo sau gate | Kill switch, alerts, runbook, rollback | Forward metrics đạt; drawdown trong hạn; security review |
| 6. Hardening | Scale nhiều EA, retention, DR, load test | Capacity report, backup/restore test | P95 latency/throughput/retention; incident drills |

**Gate bắt buộc trước Phase 4:** event semantics/sequence/idempotency/auth/410/snapshot tests xanh; EA không thể tạo duplicate order; risk limit/kill switch hoạt động; model forward metrics được review độc lập (không dùng confidence như win probability).

---

## 10. Danh sách kiểm thử nghiệm thu

### 10.1 Event semantics

| ID | Test | Kỳ vọng |
|---|---|---|
| EV-01 | Engine vào TREND_UP | Phát `UP`, tạo `trend_id` mới, `state_version` tăng, event/trend atomic |
| EV-02 | Engine vào TREND_DOWN | Phát `DOWN`, trend_id mới; không tái dùng trend_id cũ |
| EV-03 | TREND_UP kết thúc | Phát `END_UP` cùng trend_id; trend_state=ENDED; không phát `CANCEL_UP` trừ policy |
| EV-04 | TREND_DOWN kết thúc | Phát `END_DOWN` cùng trend_id |
| EV-05 | Signal bị huỷ trước execution | Phát `CANCEL_UP/DOWN`; EA không mở; trend_state=CANCELLED |
| EV-06 | UP rồi DOWN liên tiếp | `END_UP` trước `DOWN`, sequence liên tiếp, đúng thứ tự |
| EV-07 | Không đổi regime | Không sinh event; state/health vẫn trả latest |
| EV-08 | Early trend | Không phát event tradeable; hoặc event `tradeable=false` theo quyết định contract |

### 10.2 Sequence/cursor/snapshot

| ID | Test | Kỳ vọng |
|---|---|---|
| SEQ-01 | 100 event liên tiếp | Sequence tăng đúng per stream; không trùng; order đúng |
| SEQ-02 | `after_sequence` | Chỉ trả event > cursor; `next_sequence`/`has_more` đúng |
| SEQ-03 | Cursor cũ hơn retention | 410 `EVENT_CURSOR_EXPIRED`, có snapshot URL/latest sequence |
| SEQ-04 | Snapshot | State khớp event cuối; trend active/ended/cancelled đúng |
| SEQ-05 | Long-poll không event | Trả 200 events=[] sau wait; không treo quá timeout |
| SEQ-06 | Chunk limit | `limit` đúng; `has_more` đúng; không mất event |

### 10.3 Idempotency/retry

| ID | Test | Kỳ vọng |
|---|---|---|
| IDEM-01 | POST execution trùng `Idempotency-Key` + body | Trả response gốc, `duplicate=true`; không tạo order mới |
| IDEM-02 | Cùng key khác body | 409 `IDEMPOTENCY_CONFLICT` |
| IDEM-03 | Trùng `client_order_id` | Không tạo order thứ 2; trả record cũ/ lỗi theo contract |
| IDEM-04 | EA retry sau timeout | Không duplicate; broker reconciled |
| IDEM-05 | Event trùng khi poll | EA dedupe `event_id`; không action lần 2 |

### 10.4 State/restart/recovery

| ID | Test | Kỳ vọng |
|---|---|---|
| STATE-01 | `/ea/state` sau event | Khớp trend/sequence/state_version |
| STATE-02 | API restart | Event/state vẫn đọc được; cursor tiếp tục; không mất event |
| STATE-03 | EA restart | Snapshot/state cho phép reconcile; không mở trùng |
| STATE-04 | Retention prune prediction | Event/state không phụ thuộc prediction bị xoá (source link optional) |
| STATE-05 | Model version đổi | State/event phản ánh model mới; policy mismatch rõ |

### 10.5 Failure scenarios (8 tình huống bắt buộc)

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| FAIL-01 | EA mất kết nối | Event persisted; reconnect replay/snapshot; không duplicate order |
| FAIL-02 | API restart | Durable; EA retry; outbox/event không mất |
| FAIL-03 | Engine stop | Health degraded; `tradeable=false`; EA không mở mới |
| FAIL-04 | Duplicate event | EA dedupe; execution idempotent |
| FAIL-05 | Missed many events | Cursor/410/snapshot; reconcile; không replay lệnh cũ |
| FAIL-06 | Broker rejects close | Feedback REJECTED; order vẫn OPEN; alert/retry/kill switch |
| FAIL-07 | EA restart while closing | Reconcile broker ticket; không giả định closed; không gửi trùng |
| FAIL-08 | Opposite events consecutive | END cũ trước event mới; EA đóng trước mở; state đúng |

### 10.6 Auth/security/audit

| ID | Test | Kỳ vọng |
|---|---|---|
| AUTH-01 | Không có key | 401 `AUTH_MISSING` |
| AUTH-02 | Key sai/hết hạn/revoked | 401/403; audit; EA dừng an toàn |
| AUTH-03 | Scope thiếu | 403 `FORBIDDEN_SCOPE` |
| AUTH-04 | Admin JWT dùng cho EA | Từ chối; chỉ EA credential |
| AUTH-05 | Rate limit | 429 + `Retry-After`; không ảnh hưởng ingest |
| AUD-01 | Execution/event/order | Audit có request_id, actor, event/order; không log secret |
| AUD-02 | IP allowlist/TLS | Kết nối sai bị chặn; TLS bắt buộc production |

### 10.7 Data/model correctness

| ID | Test | Kỳ vọng |
|---|---|---|
| DATA-01 | Event probabilities | Khớp prediction/model version/bar; không bịa p_win |
| DATA-02 | Stale/market closed | `tradeable=false`, reason rõ; không phát event mới |
| DATA-03 | Confidence semantics | Không dùng confidence như xác suất thắng; tài liệu/EA hiểu đúng |
| DATA-04 | Model version mismatch | Event/state từ chối hoặc cancel theo policy |
| DATA-05 | Forecast no edge | BarForecast tách khỏi event; không dùng làm signal |

### 10.8 Performance/regression

| ID | Test | Kỳ vọng |
|---|---|---|
| PERF-01 | 100 EA poll đồng thời | P95 latency trong ngưỡng; không DB lock |
| PERF-02 | 1.000 event/stream | Cursor/limit đúng; index hiệu quả |
| PERF-03 | Long-poll 25s | Không giữ thread/DB connection quá lâu; timeout đúng |
| PERF-04 | Retention | Event cũ 410; snapshot còn; không xoá active |
| REG-01 | Existing API | `/regime/latest`, `/history`, auth/health vẫn hoạt động |
| REG-02 | No order endpoint | GMRAI không có endpoint gửi lệnh; chỉ EA gửi broker |
| REG-03 | Existing tests | Backend pytest/frontend build không regression |

---

## 11. Bảng dẫn chứng chính (Verified)

| Kết luận | Trạng thái | Dẫn chứng |
|---|---|---|
| Backend FastAPI | VERIFIED | `backend/app/main.py:83`; `docs/ARCHITECTURE.md:87-88` |
| DB SQLite/Postgres + Alembic | VERIFIED | `backend/app/db.py:19-32`; `docker-compose.yml:1-15`; `backend/alembic/versions/` |
| Ingestion nến qua API key | VERIFIED | `backend/app/routers/ingest.py:14-33`; `services/ingestion.py:25-...`; `collector/collector.py:81-159` |
| Collector không gửi lệnh | VERIFIED | `collector/README.md:10-11`; `docs/PROJECT_OVERVIEW.md:7` |
| Regime engine entry/exit | VERIFIED | `backend/app/ml/regime_engine.py:177-406` |
| UP/DOWN là regime labels, không event | VERIFIED | `regime_engine.py:31`, `232-321`; `models.py:188-210` |
| END/CANCEL/trend_id không có | MISSING | grep `END_UP|END_DOWN|CANCEL_UP|CANCEL_DOWN|trend_id` trong `backend/app` không có; `models.py` không có cột |
| Prediction idempotent per bar | VERIFIED | `models.py:190-195`; `services/prediction.py:144-167` |
| State snapshot lưu trong components | PARTIAL | `regime_engine.py:157-175`; `prediction.py:233-234`, `318-323` |
| Không có event/sequence/cursor API | MISSING | route list `backend/app/routers/*.py`; `routers/regime.py:13-39` |
| Cache 5s + request-driven | VERIFIED | `prediction.py:647-687` |
| Backfill prediction, không event replay | VERIFIED/PARTIAL | `prediction.py:389-...`; `worker.py:169-...` |
| Retention xoá prediction | VERIFIED | `retention.py:59-...`; `config.py:71-72` |
| Telegram dedupe kiểu event nội bộ | PARTIAL | `models.py:448-480`; `telegram.py:292-...` |
| BarForecast riêng, no edge | VERIFIED | `models.py:411-445`; `services/forecast.py:1-18`, `183-196` |
| Auth JWT + ingest API key | VERIFIED | `deps.py:21-61`; `security/auth.py:25-42`; `admin.py:307-324` |
| Health chỉ API/DB/worker | VERIFIED | `main.py:110-159` |
| Degraded inference trả UNKNOWN 200 | VERIFIED | `prediction.py:608-644` |
| Registry state machine/pair | VERIFIED | `services/registry.py:13-55`, `73-97` |
| History regenerate xoá/ghi lại segments | VERIFIED | `services/history.py:123-126`, `161`, `192` |
| `regime_segments` chỉ index theo run | VERIFIED | `models.py:379-408`; `ml/history.py:163-...` |
| Current docs say no order endpoint | VERIFIED | `docs/API_CONTRACT.md:55-65`; `docs/SECURITY.md:32-35`; `docs/ARCHITECTURE.md:34` |
| Docs schema market candle unique lệch code | VERIFIED | `docs/DATABASE_SCHEMA.md:40` vs `models.py:45-52`; DB DDL unique includes source |

---

## 12. Phụ lục: những điểm cần chốt trước khi code

1. **CANCEL semantics:** huỷ trước khi EA thực thi hay huỷ một trend đã active? Có yêu cầu EA đóng lệnh khi CANCEL không?
2. **END vs expiry:** `END_*` phát ngay khi engine rời trend, hay chờ hết `expiry_ts`? Có phát event khi permission đổi nhưng regime vẫn trend không?
3. **Early Trend:** có đưa vào event stream không? Khuyến nghị `tradeable=false`, tách khỏi UP/DOWN.
4. **Event retention:** bao nhiêu ngày? Cursor expiry và snapshot policy.
5. **Execution ownership:** EA là bên duy nhất gửi lệnh; GMRAI có cần “order intent” endpoint không? Khuyến nghị không, chỉ feedback.
6. **Risk policy:** max daily loss, max position, SL/TP, session, news filter, kill switch ai kiểm soát?
7. **Auth:** API key scope hay mTLS/HMAC; IP allowlist; key rotation; EA instance binding.
8. **Model version switch:** đóng trend cũ hay cho chạy tiếp? Event model version mismatch xử lý ra sao?
9. **Multi-symbol/multi-timeframe:** sequence/cursor theo stream; hiện chỉ XAUUSD/M15.
10. **Compliance:** EA tự giao dịch; GMRAI research-only; cần disclaimer/risk acceptance trước live.

---

## 13. Kết luận

GMRAI hiện tại **đủ nền tảng dữ liệu/model/regime để làm signal provider**, nhưng **chưa đủ hạ tầng event để EA giao dịch an toàn**. Thiếu quan trọng nhất không phải endpoint HTTP, mà là **trend lifecycle + event ID/sequence + idempotent delivery + execution feedback + EA auth/audit**. Việc thêm một endpoint `/regime/latest` cho EA chỉ giải quyết “đọc snapshot”, không giải quyết “không bỏ lỡ chuyển trạng thái, không vào lệnh trùng, không mất đồng bộ sau restart”.

Thiết kế đề xuất giữ GMRAI là **signal/research provider**, EA là **execution client**: event-sourced API + snapshot/cursor + execution feedback + heartbeat + append-only audit. Trước khi live, bắt buộc chạy shadow và demo, đồng thời xác nhận lại edge/forward metrics vì xác suất regime hiện tại **không phải xác suất thắng lệnh**.

**Không có source code, migration, endpoint hay schema nào bị thay đổi trong quá trình kiểm toán này.** Báo cáo này là tài liệu thiết kế để review trước khi triển khai.
