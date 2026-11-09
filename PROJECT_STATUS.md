# GMRAI — Project Status

> Cập nhật gần nhất: 2026-11-09 (M1–M12 hoàn thành; M13 đang chốt).

## 1. Trạng thái tổng quan

| Milestone | Trạng thái |
|---|---|
| M1 Architecture & skeleton | ✅ |
| M2 FTMO Data Collector | ✅ code + unit tests; ⚠️ MT5 integration test cần Windows+FTMO |
| M3 Backend & Database | ✅ (15 bảng, Alembic up/down verified) |
| M4 Feature Engineering | ✅ |
| M5 HMM Regime Detection | ✅ (khóa bẫy predict_proba smoothed) |
| M6 Random Forest | ✅ |
| M7 Regime Engine | ✅ |
| M8 Backtest & Walk-forward | ✅ (chạy thật qua API worker) |
| M9 Model Registry & ONNX | ✅ (parity 8e-8 ≤ 1e-5) |
| M10 Dashboard | 🏗 đang build (subagent) |
| M11 API & Security | ✅ |
| M12 Deployment preparation | ✅ (compose/Dockerfiles/nginx; chưa chạy vì máy dev không có Docker) |
| M13 Docs & audit | 🏗 |

## 2. Kết quả kiểm thử (đã chạy thật)

- **83 pytest tests xanh** (unit, leakage, HMM parity, ONNX parity, API, E2E training pipeline, collector logic).
- Seed demo 38.250 candles (M5 27k / M15 9k / H1 2.250, nhãn `synthetic_demo`), quality checks 0 gap.
- Training thật trên DB dev: HMM #1 + RF #1, variant được chọn `combined`,
  test macro-F1 0.3244 → **gate từ chối auto-approve đúng** (ngưỡng 0.55).
- Regime live qua API: `SIDEWAYS`, confidence 0.6868, permission NO_TRADE.
- Backtest walk-forward qua background worker: 7 folds, combined F1 0.3491±0.073.
- Migration `upgrade → downgrade → upgrade` OK trên SQLite temp.

## 3. Blocker & chưa hoàn thành

| Mục | Lý do | Cần gì từ người dùng |
|---|---|---|
| MT5 collector integration test | máy dev macOS, không có Windows/MT5/FTMO | chạy collector trên máy Windows (xem collector/README.md) |
| PostgreSQL integration + docker compose thật | Docker chưa cài trên máy dev | cài Docker hoặc dùng server có Docker |
| Production deploy | chưa có server/domain | cung cấp server + phê duyệt triển khai |
| Dữ liệu XAUUSD thật | chưa kết nối collector | chạy collector với tài khoản FTMO |
| Frontend | đang build bởi subagent | — |

## 4. Files chính đã tạo

- `backend/` — FastAPI app (models, routers, services, ml/, alembic, 83 tests).
- `collector/` — bộ collector MT5 đầy đủ.
- `frontend/` — Next.js dashboard (đang build).
- `scripts/seed_demo_data.py` — seed dữ liệu demo có nhãn.
- `docker-compose.yml`, `docker/` — deployment.
- `docs/` — 9 tài liệu thiết kế; root: README, INSTALLATION_GUIDE,
  OPERATIONS_GUIDE, TROUBLESHOOTING, CHANGELOG.

## 5. Bước tiếp theo

1. Hoàn tất & build frontend, tích hợp vào repo.
2. Chạy lại full test suite + commit cuối.
3. Người dùng: (a) chạy collector trên Windows + FTMO, (b) deploy lên server.
