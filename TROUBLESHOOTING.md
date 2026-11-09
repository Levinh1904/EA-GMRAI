# GMRAI — Troubleshooting

## Backend

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ModuleNotFoundError` | quên cài deps / sai Python | `cd backend && ./.venv/bin/pip install -r requirements.txt` (Python 3.12) |
| 401 khi login | sai user/pass | kiểm tra `GMRAI_ADMIN_USERNAME/PASSWORD` trong backend/.env; khởi động lại để seed |
| Login bị 429 | rate limit login (5/phút) | chờ 1 phút; cấu hình `GMRAI_LOGIN_RATE_LIMIT` |
| `database` != ok trong /health | sai DATABASE_URL | kiểm tra backend/.env, quyền truy cập DB |
| Alembic lỗi "target database is not up to date" | DB cũ | `./.venv/bin/alembic upgrade head` |
| Training job failed "Not enough data" | thiếu nến | seed/collector cần ≥ ~1500 nến M15 hợp lệ (đủ 3 TF) |
| Regime luôn UNKNOWN | chưa có model approved / dữ liệu stale | approve model đạt chuẩn; kiểm tra Data Center freshness |
| Model không tự approved | không đạt gate (F1 / false trend rate) | xem `metrics` của training run; approve thủ công chỉ khi hợp lý |

## Collector (Windows)

| Triệu chứng | Cách xử lý |
|---|---|
| "MT5 initialize failed" | MT5 Terminal chưa chạy hoặc `MT5_PATH` sai; chạy terminal trước rồi chạy collector |
| "MT5 not logged in" | đăng nhập thủ công trên terminal, hoặc cấu hình `MT5_LOGIN/PASSWORD/SERVER` trong collector/.env (chỉ trên máy local) |
| "Symbol XAUUSD not visible" | mở Market Watch trên MT5, thêm XAUUSD |
| Ingestion 401 | API key sai/thiếu — kiểm tra `GMRAI_API_KEY` khớp server |
| "Batch too large" | giảm `GMRAI_MAX_BATCH` hoặc nâng `MAX_BATCH` server (hợp lý hóa số nến backfill) |
| Checkpoint hỏng | xóa file trong `checkpoints/` rồi chạy lại `--backfill N` |

## Dữ liệu / ML

| Triệu chứng | Giải thích / xử lý |
|---|---|
| Gap báo nhiều | kiểm tra xem gap có rơi cuối tuần không (weekend không tính lỗi); nếu trong tuần → MT5 thiếu lịch sử, `--backfill` lại |
| Nến "forming" bị từ chối | đúng thiết kế — chỉ nến đã đóng được gửi |
| Feature thiếu hàng | cần ≥ 40 nến mỗi TF; xem log `Insufficient ... candles` |
| Accuracy cao bất thường | nghi ngờ leakage — chạy lại `tests/test_leakage*.py`, kiểm tra purge/embargo, KHÔNG dùng `predict_proba` của hmmlearn (smoothed) |
| ONNX parity fail | sai phiên bản onnx/skl2onnx — dùng đúng `backend/requirements.txt` |

## Frontend

| Triệu chứng | Cách xử lý |
|---|---|
| Trang trắng / lỗi fetch | kiểm tra `NEXT_PUBLIC_API_URL` trong frontend/.env.local |
| 401 liên tục | token hết hạn — đăng xuất → đăng nhập lại |
| Chart không hiển thị | tải nhiều nến — giảm limit/pagination |

## Chạy lại toàn bộ kiểm thử

```bash
cd backend && ./.venv/bin/python -m pytest -q
cd frontend && npm run build
```
