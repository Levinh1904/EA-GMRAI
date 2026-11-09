# GMRAI — Project Status

> Cập nhật sau mỗi milestone. Lần cập nhật gần nhất: M1 (2026-11-09).

## 1. Tổng quan

- **Trạng thái**: M1 hoàn thành — skeleton + tài liệu thiết kế.
- **Môi trường dev**: macOS; Python 3.12 (Homebrew, đang cài), Node 25, Git. Không có Docker (blocker cho integration test PostgreSQL).

## 2. Đã hoàn thành

### M1 — Architecture & skeleton
- Git init (branch `main`), cấu trúc repo (backend/collector/frontend/docs/scripts/docker).
- 9 tài liệu thiết kế trong `docs/`: PROJECT_OVERVIEW, ARCHITECTURE, DATABASE_SCHEMA, AI_MODEL_DESIGN, DATA_PIPELINE, TESTING_STRATEGY, DEPLOYMENT, SECURITY, ROADMAP.
- `.env.example`, `.gitignore`.

## 3. Chưa hoàn thành

- M2 → M13 (xem docs/ROADMAP.md).

## 4. Blockers

| Blocker | Ảnh hưởng | Cách giải quyết |
|---|---|---|
| Không có Windows + MT5 + FTMO trên máy dev | Collector integration test | hoàn thành code + logic test; người dùng chạy trên máy Windows |
| Không có Docker trên máy dev | PostgreSQL integration, compose | dev/test dùng SQLite; compose sẵn sàng khi có Docker |

## 5. Bước tiếp theo

1. Hoàn tất cài Python 3.12 + tạo venv backend.
2. M3: Backend FastAPI + models + Alembic.
3. M4: Feature engineering.
4. M5: HMM.
