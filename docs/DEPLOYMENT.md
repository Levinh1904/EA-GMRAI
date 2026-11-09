# GMRAI — Deployment

## 1. Môi trường

| Môi trường | DB | Mục đích |
|---|---|---|
| Development | SQLite (local) | dev nhanh, không cần Docker |
| Testing | SQLite in-memory/temp | pytest |
| Staging | PostgreSQL (docker-compose) | kiểm định trước prod |
| Production | PostgreSQL managed/self-hosted | online |

Chỉ triển khai production sau khi người dùng cung cấp quyền truy cập và phê duyệt. Không tự mua VPS/domain/cloud.

## 2. Cấu trúc Docker

`docker-compose.yml`:
- `postgres` (16, volume, healthcheck)
- `backend` (FastAPI + uvicorn, chạy alembic upgrade khi start, volume artifacts)
- `worker` (same image, chạy automation jobs)
- `frontend` (Next.js, build stage, chạy `next start`)
- `nginx` (HTTPS termination, reverse proxy, rate limit cơ bản)

Dockerfiles: `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`, `docker/nginx.conf`.

## 3. Các bước triển khai production (tối thiểu)

1. Server: Ubuntu 22.04+, cài Docker + docker compose plugin.
2. Clone repo; tạo `.env` production (secret mạnh, khác dev).
3. `docker compose up -d postgres` → đợi healthy → `docker compose run backend alembic upgrade head`.
4. `docker compose up -d`.
5. DNS → server IP; Caddy/nginx + Let's Encrypt cho HTTPS.
6. Tạo admin user; tạo API key cho collector.
7. Collector trên Windows: cấu hình `collector/.env` → chạy → xác nhận dữ liệu vào DB.
8. Kiểm tra health, dashboard, logs.

## 4. Backup & restore

```bash
pg_dump "$GMRAI_DATABASE_URL" -Fc -f backup_$(date +%F).dump   # hàng ngày (cron)
pg_restore -d "$GMRAI_DATABASE_URL" backup_YYYY-MM-DD.dump
```
Artifacts (models) + backup DB phải nằm ngoài volume chứa DB.

## 5. Migration

- `alembic upgrade head` trong quá trình deploy (backend container tự chạy khi `AUTO_MIGRATE=true`).
- Trước migration quan trọng: backup DB bắt buộc.
- Rollback: `alembic downgrade -1` khi migration có hỗ trợ downgrade.

## 6. Monitoring & health

- `GET /api/v1/health`: DB check, worker check, data freshness.
- `GET /api/v1/system/status`: collector last sync, candle counts, stale status.
- Logs: JSON stdout trong container (docker logs); system_logs table cho sự kiện hệ thống.
- Cảnh báo: dashboard Data Center hiển thị stale/gap; (tùy chọn) webhook cảnh báo sau này.

## 7. Hạn chế hiện tại (máy dev)

- Docker chưa cài trên máy dev → compose chưa chạy thực tế ở đây; cấu hình được validate bằng `docker compose config` khi có Docker.
- Collector cần Windows + MT5 (xem collector/README.md).
