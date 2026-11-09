# GMRAI — Operations Guide

## 1. Vận hành hàng ngày

| Việc | Tần suất | Ở đâu |
|---|---|---|
| Kiểm tra data freshness / stale | mỗi ngày | Dashboard → Data Center |
| Xem regime hiện tại + reason codes | mỗi ngày | Overview |
| Kiểm tra collector status | mỗi ngày | Data Center → sync logs |
| Quality check | tự động + thủ công | Data Center → Run check |
| Retrain | tự động (nếu bật automation) hoặc thủ công | Training Center |

Chu kỳ tự động (bật khi `GMRAI_AUTOMATION_ENABLED=true`):
- Quality check M5/M15/H1: `GMRAI_SYNC_CHECK_INTERVAL_SECONDS` (mặc định 300s).
- Retrain khi có ≥ `GMRAI_MIN_NEW_CANDLES_FOR_RETRAIN` nến M15 mới.

## 2. Quy trình model lifecycle

1. **Training Center → Start** (hoặc tự động): tạo HMM + RF, đánh giá
   train/val/test theo thời gian, export ONNX + parity check.
2. Kết quả: model có `test_macro_f1 ≥ GMRAI_APPROVE_MIN_F1` **và**
   `false_trend_rate ≤ GMRAI_APPROVE_MAX_FALSE_TREND_RATE` → tự động
   `approved`. Không đạt → `candidate`, admin xem xét thủ công
   (Model Registry → Approve/Reject). **Không bao giờ approve model không
   đạt kiểm định.**
3. Model mới approved tự động được dùng cho regime/latest (lấy version
   mới nhất). Model cũ → Archive khi cần.
4. Chạy backtest walk-forward trước khi approve quan trọng; so sánh
   HMM-only / RF-only / HMM+RF — chỉ chọn ensemble khi OOS tốt hơn.

## 3. Backup & restore

```bash
# Hàng ngày (cron) — backup DB + artifacts:
pg_dump "$DATABASE_URL" -Fc -f /backups/gmrai_$(date +%F).dump
tar czf /backups/artifacts_$(date +%F).tgz -C /path/to/artifacts .
# Artifacts phải nằm ngoài volume chứa DB.

# Restore:
pg_restore -d "$DATABASE_URL" /backups/gmrai_YYYY-MM-DD.dump
```

## 4. Migration database

- Container backend tự chạy `alembic upgrade head` khi start.
- **Trước migration quan trọng: backup DB bắt buộc.**
- Rollback: `alembic downgrade -1` (migration hỗ trợ downgrade).
- Thêm migration mới: sửa models → `alembic revision --autogenerate -m "..."`.

## 5. Monitoring

- `GET /api/v1/health`: API/DB/worker.
- `GET /api/v1/system/status`: candle counts, active models, recent jobs.
- Logs: `docker compose logs -f backend worker` + System logs trong Settings.
- Cảnh báo stale: Dashboard hiển thị đỏ khi dữ liệu cũ hơn ngưỡng
  (M5 30ph / M15 60ph / H1 240ph — cấu hình trong .env).

## 6. API cho EA (tương lai)

EA có thể gọi `GET /api/v1/regime/latest` (Bearer token) và nhận
`regime`, `confidence`, `probabilities`, `permission`, `expiry`,
`reason_codes`. **Đây là kết quả nghiên cứu — không có endpoint gửi lệnh,
không quản lý vốn.** Nếu dữ liệu cũ/model lỗi → `UNKNOWN` + `NO_TRADE`.

## 7. Secret management

- Secrets chỉ trong `.env` (không commit). Xoay vòng định kỳ:
  `GMRAI_SECRET_KEY`, `GMRAI_API_KEY`, password admin/DB.
- API key mới cho collector: thêm vào bảng `api_keys` (hash) hoặc dùng
  giá trị `GMRAI_API_KEY` (seed tự động thành key `env-bootstrap`).
