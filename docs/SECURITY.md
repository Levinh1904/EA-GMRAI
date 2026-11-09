# GMRAI — Security

## 1. Bí mật (secrets)

- KHÔNG commit: mật khẩu MT5/FTMO, API key, token, secret vào Git.
- `.env` nằm trong `.gitignore`; mỗi môi trường có `.env` riêng.
- Template: `.env.example` (chỉ chứa placeholder).
- MT5 credentials chỉ nhập trên máy chạy Collector (không gửi qua chat).

## 2. Authentication & phân quyền

- **Dashboard/API người dùng**: JWT (HS256, `GMRAI_SECRET_KEY` ≥ 32 bytes), expiry 12h. Bcrypt hash password (cost 12).
- **Roles**: `admin` (full), `analyst` (đọc + chạy training/backtest).
- **Collector ingestion**: API key riêng (`X-API-Key`), lưu dạng SHA-256 hash trong bảng `api_keys`; không dùng JWT cho ingestion (collector không interactive login).
- Tất cả endpoint trừ `/health`, `/auth/login`, `/docs` yêu cầu xác thực.

## 3. Rate limiting

- `slowapi`: login 5 lần/phút/IP; API chung 120 req/phút/token; ingestion 30 req/phút/key.

## 4. Input validation

- Pydantic schema nghiêm ngặt cho mọi request.
- Ingestion: validate OHLC (dương, high≥max(o,c), low≤min(o,c)), từ chối nến chưa đóng, giới hạn batch size (≤ 10.000 nến/request).
- SQLAlchemy parameterized queries (không SQL injection).

## 5. HTTPS & vận chuyển

- Production: TLS qua nginx/Caddy + Let's Encrypt; redirect HTTP→HTTPS.
- Collector gọi API qua HTTPS với cert verification; header `X-Collector-ID` để audit.

## 6. API cho EA (tương lai)

- Read-only: `/api/v1/regime/latest` là nguồn kết quả phân tích.
- KHÔNG có endpoint gửi lệnh, quản lý vốn, SL/TP — phạm vi tuyệt đối cấm trong giai đoạn này.

## 7. Auditing & logs

- `system_logs`: đăng nhập thất bại, migration, model status changes.
- Không log password/key/token dưới bất kỳ dạng nào.

## 8. Backups

- pg_dump hàng ngày (xem DEPLOYMENT.md); backup trước mọi migration quan trọng.
