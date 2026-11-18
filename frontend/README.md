# GMRAI Frontend

Dashboard frontend cho GMRAI (Gold Market Regime AI Intelligence) — nền tảng phân tích chế độ
thị trường vàng XAUUSD bằng AI định lượng (HMM + Random Forest).

## Stack

- **Next.js 15** (App Router) + **TypeScript** (strict)
- **Plotly.js** qua `react-plotly.js` — các biểu đồ load động (`dynamic(..., { ssr: false })`)
- **SWR** cho data fetching + polling trạng thái job
- Plain **CSS Modules**, giao diện dark theme kiểu quant-trading
- Giao tiếp API: `fetch` + Bearer token, client API tập trung tại `lib/api.ts`

## Yêu cầu

- Node >= 18.18 (đã test với Node 25), npm
- Backend FastAPI chạy ở `http://localhost:8000` (CORS đã cho phép `http://localhost:3000`)

## Cài đặt & chạy

```bash
npm install
npm run dev        # dev server tại http://localhost:3000
npm run build      # production build
npm start          # chạy bản build (cần build trước)
```

## Biến môi trường

| Biến                  | Mặc định                 | Mô tả                          |
| --------------------- | ------------------------ | ------------------------------ |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000`  | Base URL backend (không có `/`) |

Copy `.env.example` thành `.env.local` nếu cần đổi địa chỉ backend (đổi biến này cần rebuild).
Frontend gọi tất cả endpoint qua `<NEXT_PUBLIC_API_URL>/api/v1/...`.

## Đăng nhập

- Trang `/login`. Mật khẩu admin lấy từ `backend/.env` (sinh bằng `python -m scripts.rotate_secrets`).
- Token lưu ở `localStorage` (key `gmrai_access_token`), gắn header `Authorization: Bearer <token>`.
- Mọi response 401 sẽ tự xóa token và redirect về `/login`.
- Vai trò `admin` mở khóa các hành động: khởi động training, khởi động backtest,
  duyệt/từ chối/lưu trữ model, chạy kiểm tra chất lượng dữ liệu.

## Các trang

| Route          | Nội dung                                                          |
| -------------- | ----------------------------------------------------------------- |
| `/`            | Tổng quan: regime hiện tại, độ tươi dữ liệu, xác suất HMM/RF       |
| `/market`      | Biểu đồ nến (M5/M15/H1), EMA20, nền regime, phân trang offset     |
| `/regime`      | AI Regime: posterior HMM, state mapping, transmat, engine params  |
| `/training`    | Form khởi động huấn luyện + danh sách job (polling trạng thái)    |
| `/backtesting` | Walk-forward: form, danh sách, so sánh biến thể (mean ± std)      |
| `/compare`     | So sánh HMM-only vs RF-only vs HMM+RF (backtest + training + registry) |
| `/models`      | Model Registry: trạng thái phiên bản, tải artifact/ONNX, duyệt     |
| `/data`        | Data Center: số nến, độ tươi, sync logs, quality reports          |
| `/settings`    | Trạng thái hệ thống, logs, kết nối API, tài khoản                 |

## Cấu trúc

```
app/                # routes (route group (app) bọc AppShell + auth guard)
  login/            # trang đăng nhập (không cần shell)
components/
  AppShell.tsx      # sidebar + topbar (regime badge) + DEMO banner + footer
  AuthProvider.tsx  # context xác thực (login/logout/role)
  charts/           # Plotly: candlestick+EMA, regime strip, variant compare
  ui/               # Card, Badge, Notice, Table primitives, states...
lib/
  api.ts            # API client typed + token + 401 redirect
  types.ts          # toàn bộ type domain theo contract backend
  regime.ts         # color map, labels, reason codes
  market.ts         # EMA, align regime per candle
types/              # ambient typings cho plotly.js và react-plotly.js
```

## Ghi chú quan trọng

- **DEMO DATA**: khi `regime/latest` trả `data_source: "synthetic_demo"`, mọi trang hiển thị
  banner vàng "DEMO DATA — synthetic, not live market data". Không bao giờ trình bày dữ liệu
  demo như dữ liệu thị trường thật.
- Quyền giao dịch (`BUY_ONLY`/`SELL_ONLY`/`NO_TRADE`) luôn kèm disclaimer
  "Nghiên cứu — không phải lệnh giao dịch".
- Toàn bộ thời gian hiển thị theo UTC kèm nhãn "UTC".
- Footer disclaimer: "GMRAI là công cụ nghiên cứu. Kết quả phân tích không phải lời khuyên đầu
  tư và không gửi lệnh giao dịch." kèm nguồn dữ liệu.
- `/ingest/status` trả về key `recent_syncs` (khác với `last_sync` trong `/stats/dashboard`).
- Báo cáo walk-forward chi tiết nằm server-side trong artifacts; API chỉ trả metrics tóm tắt.
