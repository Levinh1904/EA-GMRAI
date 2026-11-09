# GMRAI — Testing Strategy

## 1. Nguyên tắc

- Mỗi module có test; không đánh dấu tính năng hoàn thành nếu chưa có test phù hợp.
- Không bỏ qua test thất bại; không giả lập thành công (đặc biệt FTMO connection).
- Test nào không chạy được do thiếu MT5/Windows/cloud → ghi rõ lý do + điều kiện + cách chạy.

## 2. Tầng test

| Tầng | Công cụ | Phạm vi |
|---|---|---|
| Unit | pytest | features, HMM inference, mapping, labels, regime engine, splits, metrics |
| Leakage | pytest | causality của filtered posterior, purge/embargo, no-lookahead của feature |
| API | pytest + httpx TestClient | auth, ingestion upsert, pagination, regime UNKNOWN khi không có dữ liệu, health |
| DB | pytest + SQLite temp | migration apply, unique constraint, indexes |
| Data quality | pytest | gap/duplicate/bad-candle/stale detection |
| ONNX parity | pytest + onnxruntime | Python vs ONNX (tol 1e-5), HmmFilter vs hmmlearn (tol 1e-6) |
| Backtest | pytest | cấu trúc walk-forward, metrics tính đúng, không rò rỉ giữa các fold |
| Frontend | vitest + next build | API client, component smoke; E2E playwright khi chạy đủ services |
| Integration | pytest (SQLite) + docker-compose (staging) | luồng ingest → features → train → predict → ONNX end-to-end |

## 3. Các test leakage quan trọng

1. **Filtered posterior causal**: posterior tại t của chuỗi [0..t] == posterior tại t của chuỗi [0..t+k] với mọi k (bất biến với tương lai).
2. **Warm-up restart**: posterior sau restart (replay window) == posterior chạy liên tục (sai số float nhỏ).
3. **Feature no-lookahead**: feature tại t chỉ thay đổi khi thêm dữ liệu trước t; thêm dữ liệu sau t không đổi feature tại t.
4. **Purge/embargo**: không tồn tại cặp (train, test) cách nhau < embargo; label window không tràn vào test.
5. **Scaler fit on train**: mean/std dùng để transform test lấy từ train.

## 4. Quality gate trước khi kết thúc mỗi milestone

1. Chạy test liên quan → xanh.
2. Kiểm tra log không lỗi.
3. Sửa lỗi → chạy lại.
4. Kiểm tra regression (full suite).
5. Cập nhật PROJECT_STATUS.md + commit Git.

## 5. Lệnh

```bash
cd backend
python -m pytest -q                      # toàn bộ
python -m pytest tests/test_leakage.py   # riêng leakage
cd ../frontend
npm run build && npm test                # frontend
```

## 6. Test chưa chạy được trên máy dev (blocker)

| Test | Lý do chưa chạy | Điều kiện | Cách chạy |
|---|---|---|---|
| MT5 collector integration | không có Windows/MT5/FTMO account trên máy dev | Windows + MT5 Terminal đăng nhập FTMO | xem collector/README.md |
| PostgreSQL integration | Docker chưa cài | Docker hoặc PostgreSQL local | `docker compose up -d postgres` + `GMRAI_DATABASE_URL=postgresql://...` |
| E2E trình duyệt | cần đủ services | chạy backend+frontend | xem INSTALLATION_GUIDE.md |
