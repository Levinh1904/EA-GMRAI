# GMRAI — Roadmap

## Milestones

| # | Milestone | Nội dung | Tiêu chí hoàn thành |
|---|---|---|---|
| M1 | Architecture & skeleton | repo, docs thiết kế, cấu trúc dự án | 9 docs + skeleton + commit |
| M2 | FTMO Data Collector | collector.py, mt5_client.py, data_sync.py, api_client.py, logger.py, config.py | code hoàn chỉnh, README, unit-test được phần logic sync (MT5 integration test cần Windows) |
| M3 | Backend & Database | FastAPI, models, Alembic, auth, ingestion | migration chạy, API test xanh |
| M4 | Features | M15/H1/M5 features, versioning, quality checks | unit test công thức + leakage test |
| M5 | HMM | GaussianHMM 5 states, mapping, causal inference | train chạy thật, parity HmmFilter, mapping có bằng chứng |
| M6 | Random Forest | labels, purge/embargo, tuning, so sánh ensemble | OOS đánh giá, chọn ensemble theo tiêu chí |
| M7 | Regime Engine | thresholds, hysteresis, confirmation, reason codes | thresholds tối ưu trên validation, test trên test-set |
| M8 | Backtest & Walk-forward | expanding/rolling, purge/embargo, metrics, simulation | báo cáo metrics đầy đủ |
| M9 | Registry & ONNX | model registry, ONNX RF, parity tests | parity xanh, export hoạt động |
| M10 | Dashboard | 9 trang Next.js | build xanh, hiển thị dữ liệu thật từ API |
| M11 | API & Security | versioned API, JWT, rate limit, health | API tests + security tests xanh |
| M12 | Integration & Deployment | docker compose, Dockerfiles, nginx, E2E | compose config hợp lệ, docs triển khai |
| M13 | Documentation & Audit | README, INSTALLATION, OPERATIONS, TROUBLESHOOTING, CHANGELOG, PROJECT_STATUS | bàn giao đầy đủ |

## Quy tắc

- Không bắt đầu milestone mới nếu milestone trước có lỗi nghiêm trọng chưa xử lý.
- Mỗi milestone: task list + tiêu chí + test + báo cáo + Git commit.
- Một nguồn sự thật cho cấu hình (`.env.example` mỗi component + docs này).
- Có thể dùng subagents cho frontend/QA nhưng kiến trúc thống nhất do main agent chốt.

## Blockers đã biết

1. **MT5/Windows**: collector không test được trên macOS → ghi rõ, hoàn thành tối đa phần logic.
2. **Docker không có trên máy dev**: PostgreSQL integration test + compose chạy thật chờ môi trường có Docker (hoặc người dùng cài).
3. **Production**: cần người dùng cung cấp server + phê duyệt.
