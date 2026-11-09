# GMRAI — Installation Guide

## 1. Yêu cầu

| Môi trường | Thành phần |
|---|---|
| Development (macOS/Linux) | Python 3.12, Node 20+, (PostgreSQL tùy chọn) |
| Collector | Windows 10/11 + MetaTrader 5 Terminal + tài khoản FTMO |
| Production | Server Ubuntu 22.04+, Docker + docker compose plugin |

## 2. Development (local, SQLite — không cần Docker)

```bash
git clone <repo> && cd GMRAI

# Backend
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env            # chỉnh GMRAI_SECRET_KEY, ADMIN_PASSWORD nếu cần
./.venv/bin/alembic upgrade head            # hoặc để AUTO_CREATE_TABLES=true tự tạo
./.venv/bin/python ../scripts/seed_demo_data.py --bars 9000 --train   # dữ liệu demo (tùy chọn)
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd ../frontend
npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev                     # http://localhost:3000
```

Đăng nhập admin mặc định: `admin` / `admin-change-me` (đổi trong backend/.env).

## 3. Production (Docker Compose + PostgreSQL)

```bash
# Trên server:
git clone <repo> && cd GMRAI
cp .env.example .env && vi .env
# Bắt buộc: GMRAI_SECRET_KEY (openssl rand -hex 32), GMRAI_ADMIN_PASSWORD,
# POSTGRES_PASSWORD, GMRAI_API_KEY, GMRAI_CORS_ORIGINS=https://domain-của-bạn

docker compose up -d postgres
docker compose run --rm backend sh -c "alembic upgrade head"
docker compose up -d
# Truy cập http://<ip>/ — health: curl http://<ip>/api/v1/health
```

`backend` container tự chạy `alembic upgrade head` khi start (GMRAI_AUTO_MIGRATE=true).

### HTTPS
- Cách A (đơn giản): trỏ DNS → server, cài Caddy: `caddy reverse-proxy --from domain --to localhost:80`.
- Cách B: certbot/cert vào `docker/certs/`, bật khối TLS trong `docker/nginx.conf` (đã có sẵn bản mẫu).

## 4. Collector (Windows + MT5 FTMO)

Xem [collector/README.md](collector/README.md):
1. Cài Python 3.10–3.12 + MT5 Terminal (đăng nhập FTMO thủ công).
2. `pip install -r collector/requirements.txt`, copy `.env.example` → `.env`.
3. `python collector.py --backfill 365`.
4. Xác nhận dữ liệu lên dashboard → Data Center.

> Mật khẩu MT5/FTMO chỉ nhập trên máy chạy collector. KHÔNG bao giờ đưa vào chat/Git.

## 5. Kiểm tra sau cài đặt

```bash
curl http://localhost:8000/api/v1/health           # {"api":"ok","database":"ok",...}
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"..."}'
```

Sau khi có dữ liệu: chạy quality check (Data Center), training (Training
Center), kiểm tra regime/latest, approve model đạt ngưỡng, chạy backtest
walk-forward.
