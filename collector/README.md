# GMRAI FTMO MT5 Data Collector — Hướng dẫn

Collector chạy trên **Windows** (PC hoặc VPS) đã cài **MetaTrader 5 Terminal**
và đã đăng nhập tài khoản **FTMO** (FTMO-Server4). Nó đọc nến XAUUSD
M5/M15/H1, chỉ gửi nến đã đóng lên GMRAI Ingestion API qua HTTPS.

> **Chú ý quan trọng**
> - KHÔNG gửi mật khẩu MT5/FTMO cho bất kỳ ai (kể cả qua chat).
>   Mật khẩu chỉ nhập trực tiếp trên máy chạy collector (file `.env` local
>   hoặc đăng nhập thủ công trên MT5 Terminal).
> - Collector không gửi lệnh giao dịch — chỉ thu thập dữ liệu nến.

## 1. Chuẩn bị

1. Cài Python 3.10–3.12 trên Windows (python.org).
2. Cài MT5 Terminal, đăng nhập tài khoản FTMO (nhập mật khẩu trực tiếp
   trên terminal), bật hiển thị XAUUSD trong Market Watch.
3. Copy thư mục `collector/` lên máy Windows.

## 2. Cài đặt

```bat
cd collector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Sửa `.env`:
- `GMRAI_INGEST_URL` + `GMRAI_API_KEY`: địa chỉ + API key của GMRAI server.
- `MT5_PATH`: đường dẫn terminal64.exe (nếu muốn collector tự mở terminal).
- `MT5_LOGIN/MT5_PASSWORD/MT5_SERVER`: **tùy chọn** — nếu để trống, bạn
  đăng nhập thủ công trên MT5 Terminal rồi mới chạy collector.

## 3. Chạy

```bat
:: Backfill 365 ngày lịch sử rồi chạy đồng bộ định kỳ
python collector.py --backfill 365

:: Hoặc chạy định kỳ bình thường (60 giây/chu kỳ theo .env)
python collector.py
```

- Nến **đang hình thành** không bao giờ được gửi.
- Mỗi chu kỳ resync lại 50 nến gần nhất (upsert) để xử lý cập nhật muộn.
- Checkpoint lưu trong `checkpoints/` — sau khi restart, collector tiếp tục
  đúng chỗ, không gửi lại toàn bộ.
- Log xoay vòng trong `logs/collector.log`.

## 4. MT5 mất kết nối

Collector tự phát hiện (`MT5 terminal is not connected`), shutdown, chờ
backoff (10s → tối đa 300s) và kết nối lại. Bạn chỉ cần can thiệp nếu
terminal bị logout hoàn toàn — đăng nhập lại trên terminal là xong.

## 5. Kiểm tra dữ liệu đã lên server

Mở dashboard GMRAI → **Data Center**: xem collector status, last sync,
candle counts, gaps, duplicates. Dữ liệu thiếu (gap) được báo cáo, KHÔNG
tự chế dữ liệu thay thế.

## 6. Lưu ý về lịch sử

- Không giả định MT5 có sẵn 2–3 năm lịch sử; kiểm tra số nến thực tế
  (log + Data Center).
- Nếu thiếu lịch sử xa: chạy `--backfill N` với N lớn hơn và xác nhận
  số nến nhận được trên dashboard.

## 7. Blocker đã biết (môi trường phát triển)

Máy dev hiện tại là macOS, không có Windows/MT5/tài khoản FTMO nên phần
kết nối MT5 **chưa được kiểm thử tích hợp thực tế**. Các module logic
(config, logger, api_client, data_sync) có unit test độc lập trong
`backend/tests/test_collector_logic.py` (chạy xanh trên mọi nền tảng).
