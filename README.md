# GMRAI — Gold Market Regime AI Intelligence

Nền tảng thu thập dữ liệu, nghiên cứu, huấn luyện, kiểm định, so sánh và
quản lý các mô hình AI phân tích **chế độ thị trường (market regime)** của
vàng **XAUUSD** (broker FTMO, khung chính M15 + context H1 + timing M5).

> ⚠️ **GMRAI là công cụ NGHIÊN CỨU.** Hệ thống KHÔNG gửi lệnh giao dịch,
> không kết nối tài khoản để giao dịch, không quản lý vốn/SL/TP.
> Kết quả phân tích không phải lời khuyên đầu tư.

## Thành phần

| Thành phần | Công nghệ | Mô tả |
|---|---|---|
| [collector/](collector/) | Python + MetaTrader5 lib (Windows) | Thu thập nến XAUUSD M5/M15/H1 từ MT5 (FTMO), gửi lên cloud qua HTTPS |
| [backend/](backend/) | FastAPI + SQLAlchemy + PostgreSQL | Ingestion, quality checks, features, HMM + Random Forest, regime engine, backtest, model registry, ONNX export, API v1 |
| [frontend/](frontend/) | Next.js + Plotly | Dashboard 9 trang (Overview, Live Market, AI Regime, Training, Backtesting, Model Comparison, Registry, Data Center, Settings) |
| [docs/](docs/) | — | Thiết kế kiến trúc, schema, AI model, pipeline, testing, deployment, security, roadmap |

## Bắt đầu nhanh (development, không cần MT5)

```bash
cd backend
python3.12 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env                      # sửa secret nếu cần
./.venv/bin/python ../scripts/seed_demo_data.py --bars 9000 --train   # dữ liệu DEMO có nhãn rõ
./.venv/bin/uvicorn app.main:app --port 8000

cd ../frontend
npm install && npm run dev                # http://localhost:3000
```

Đăng nhập: `admin` / `admin-change-me` (đổi trong `.env` trước khi dùng thật).
Dữ liệu seed là **synthetic_demo** — dashboard hiển thị banner DEMO rõ ràng,
không bao giờ giả làm dữ liệu live.

## Cấu hình thật (MT5 + FTMO)

1. Triển khai backend + PostgreSQL (xem [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md), `docker-compose.yml`).
2. Chạy collector trên Windows có MT5 đăng nhập FTMO (xem [collector/README.md](collector/README.md)).
3. Kiểm tra Data Center → training → approve model → regime live.

## Kiểm thử

```bash
cd backend && ./.venv/bin/python -m pytest -q      # 83 tests: unit, leakage, parity, API, E2E
cd frontend && npm run build
```

Các test leakage quan trọng: filtered posterior causal (KHÔNG dùng
`hmmlearn.predict_proba` — nó smoothed, nhìn tương lai), purge/embargo,
feature no-lookahead, warmup restart.

## Tài liệu

- [PROJECT_STATUS.md](PROJECT_STATUS.md) — tiến độ thực tế, blockers
- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) — cài đặt đầy đủ
- [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md) — vận hành, backup, migration
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — sự cố thường gặp
- [CHANGELOG.md](CHANGELOG.md)
- [docs/](docs/) — 9 tài liệu thiết kế
