# GMRAI — Gold Market Regime AI Intelligence

## 1. Tổng quan

GMRAI là nền tảng thu thập dữ liệu, nghiên cứu, huấn luyện, kiểm định, so sánh và quản lý các mô hình AI phân tích **chế độ thị trường (market regime)** của vàng XAUUSD.

**Phạm vi hiện tại:** phân tích AI (nghiên cứu). KHÔNG gửi lệnh giao dịch, KHÔNG kết nối tài khoản để giao dịch, KHÔNG quản lý vốn/SL/TP, KHÔNG can thiệp tài khoản FTMO. API có thể được EA tích hợp trong tương lai nhưng hiện tại chỉ phục vụ truy xuất kết quả phân tích.

## 2. Cấu hình đã chốt

| Hạng mục | Cấu hình |
|---|---|
| Tên dự án | GMRAI |
| Thị trường / Symbol | Gold / XAUUSD |
| Broker / tài khoản | FTMO Challenge (FTMO-Server4) |
| Nguồn dữ liệu | FTMO MT5 Terminal |
| Timeframes | M5, M15, H1 |
| Regime chính | M15 |
| Context | H1 |
| Timing | M5 |
| HMM | Gaussian HMM, 5 hidden states, diagonal covariance |
| Supervised model | Random Forest |
| Model export | ONNX |
| Frontend | Next.js / React (TypeScript) |
| Backend | Python FastAPI |
| Database | PostgreSQL (dev/test fallback: SQLite) |
| AI/ML | Python 3.12, hmmlearn, scikit-learn, skl2onnx |
| Charts | Plotly |
| Deployment | Docker Compose (online, sau khi được phê duyệt) |

## 3. Mục tiêu hệ thống

1. Thu thập dữ liệu XAUUSD M5/M15/H1 từ MT5 (FTMO) lên cloud qua HTTPS.
2. Lưu trữ, kiểm soát chất lượng dữ liệu (gap, duplicate, stale, candle lỗi).
3. Feature engineering đa timeframe, phiên bản hóa, không lookahead.
4. Huấn luyện Gaussian HMM 5 hidden states; ánh xạ hidden state → semantic regime qua thống kê tập train (không ép gán).
5. Huấn luyện Random Forest bổ trợ; so sánh HMM-only / RF-only / HMM+RF ngoài mẫu.
6. Operational Regime Engine: SIDEWAYS, TREND_UP, TREND_DOWN, EARLY_TREND_UP/DOWN, TRANSITION, HIGH_VOLATILITY, UNKNOWN.
7. Backtest & walk-forward validation theo thứ tự thời gian (purge/embargo, không shuffle).
8. Model Registry (version, status, metrics, artifacts) + export ONNX + parity tests.
9. Dashboard web hiển thị dữ liệu, regime, training, backtest, registry.
10. API versioned `/api/v1` để EA tích hợp trong tương lai.

## 4. Nguyên tắc tối thượng

- **Tính đúng đắn của dữ liệu**: chỉ dùng nến đã đóng; upsert; không tự chế dữ liệu thay thế dữ liệu thiếu; không hiển thị dữ liệu giả như dữ liệu live (dữ liệu demo luôn được gắn nhãn rõ ràng).
- **Không lookahead bias, không data leakage**: scaler fit trên train; label chỉ dùng tương lai làm target, không vào feature; inference tại t chỉ dùng dữ liệu đến t (filtered posterior, không Viterbi smoothing, không smoothing toàn chuỗi).
- **Khả năng tái lập**: feature version, model version, dataset range, hyperparameters, seed — lưu đầy đủ trong registry.
- **Trung thực kết quả**: không công bố accuracy nếu chưa có test thực tế; không giả vờ chạy thành công.

## 5. Cấu trúc repository

```
GMRAI/
├── backend/            # FastAPI + ML pipeline + Alembic + tests
│   ├── app/
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic schemas
│   │   ├── routers/    # API routers (v1)
│   │   ├── services/   # business logic
│   │   ├── ml/         # features, hmm, rf, regime engine, backtest, onnx
│   │   └── security/   # JWT, password, api key
│   ├── alembic/        # migrations
│   └── tests/
├── collector/          # FTMO MT5 Data Collector (Windows)
├── frontend/           # Next.js dashboard
├── scripts/            # seed demo data, dev tools
├── docker/             # Dockerfiles, nginx
├── docs/               # tài liệu
└── docker-compose.yml
```

## 6. Milestones

M1 Architecture & skeleton → M2 FTMO Collector → M3 Backend & DB → M4 Features → M5 HMM → M6 RF → M7 Regime Engine → M8 Backtest/Walk-forward → M9 Registry & ONNX → M10 Dashboard → M11 API & Security → M12 Integration testing & deployment → M13 Documentation & audit.

Chi tiết ở [ROADMAP.md](ROADMAP.md). Tiến độ thực tế ở `PROJECT_STATUS.md` (root).

## 7. Môi trường hiện tại (ghi nhận thực tế)

- macOS, Python 3.12 (Homebrew), Node 25, Git.
- **Docker chưa cài trên máy dev** → dev/test chạy bằng SQLite; PostgreSQL được cấu hình qua docker-compose cho môi trường staging/production.
- Collector chỉ chạy trên Windows có MT5 + tài khoản FTMO — chưa thể kiểm thử trên máy này; sẽ ghi rõ blocker.
