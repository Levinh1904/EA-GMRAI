# GMRAI — Project Status

> Cập nhật cuối: 2026-11-09 — **M1–M13 hoàn thành. Bàn giao v0.1.0.**

## 1. Trạng thái milestones

| Milestone | Trạng thái |
|---|---|
| M1 Architecture & skeleton | ✅ |
| M2 FTMO Data Collector | ✅ code + unit tests; ⚠️ MT5 integration cần Windows+FTMO |
| M3 Backend & Database | ✅ |
| M4 Feature Engineering | ✅ |
| M5 HMM Regime Detection | ✅ (khóa bẫy `predict_proba` smoothed) |
| M6 Random Forest | ✅ |
| M7 Regime Engine | ✅ |
| M8 Backtest & Walk-forward | ✅ |
| M9 Model Registry & ONNX | ✅ |
| M10 Dashboard (Next.js, 9 trang) | ✅ build xanh + QA trình duyệt thật |
| M11 API & Security | ✅ |
| M12 Deployment preparation | ✅ (compose/Dockerfiles/nginx; chưa chạy do máy dev không có Docker) |
| M13 Docs & audit | ✅ |

## 2. Kết quả đã chạy thật (không mô phỏng)

- **82 pytest tests xanh** (unit, leakage, HMM parity 1e-10, ONNX parity ≤1e-5
  đo được 8e-8, API, E2E training, collector logic).
- Seed demo 38.250 candles (`synthetic_demo`, nhãn rõ), quality checks 0 gap.
- Training thật trên DB dev: chọn variant `combined`; test F1 0.3244 →
  **gate từ chối auto-approve đúng** (ngưỡng 0.55); approve thủ công qua API.
- Regime live qua API: SIDEWAYS 68.7%, NO_TRADE, reason codes đầy đủ.
- Backtest walk-forward qua background worker: 7 folds, combined F1 0.3491±0.073.
- Migration alembic up → down → up OK.
- Frontend: `npm run build` xanh; QA bằng trình duyệt thật (login → Overview,
  Market với 2 biểu đồ Plotly render, AI Regime với posterior/engine params/
  state mapping) — banner DEMO + cảnh báo stale hoạt động đúng.

## 3. Blocker còn lại (cần người dùng)

| Blocker | Cần gì |
|---|---|
| MT5 collector integration test | máy Windows + MT5 + tài khoản FTMO (xem collector/README.md) |
| PostgreSQL/docker compose chạy thật | máy có Docker (hoặc server) |
| Production deploy | server/domain + phê duyệt triển khai |
| Dữ liệu XAUUSD thật | chạy collector với tài khoản FTMO |

## 4. Cấu trúc bàn giao

```
GMRAI/
├── backend/     FastAPI + ML (HMM/RF/regime/backtest/ONNX) + Alembic + 82 tests
├── collector/   FTMO MT5 Data Collector (Windows)
├── frontend/    Next.js dashboard (9 trang)
├── docs/        10 tài liệu (thiết kế + API_CONTRACT)
├── scripts/     seed_demo_data.py
├── docker/      Dockerfiles + nginx.conf
├── docker-compose.yml
├── README.md / INSTALLATION_GUIDE.md / OPERATIONS_GUIDE.md /
│   TROUBLESHOOTING.md / CHANGELOG.md / PROJECT_STATUS.md
```

## 5. Bước tiếp theo cho người dùng

1. Chạy collector trên Windows có MT5 + FTMO (dữ liệu thật).
2. Deploy lên server (docker compose) khi có server/domain.
3. Theo dõi Training Center/Backtesting; approve model đạt gate; EA có thể
   đọc `GET /api/v1/regime/latest` (nghiên cứu, không gửi lệnh).
