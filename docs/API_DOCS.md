# TÀI LIỆU REST API & WEBSOCKET

## 1. WebSocket Real-time
- **URL:** `ws://<HOST>:8000/ws/station`
- **Các sự kiện đẩy từ Backend:**
  - `snapshot`: Ảnh chụp trạng thái ban đầu khi client kết nối.
  - `telemetry`: Đẩy định kỳ ~10Hz gồm `weight_gram`, `is_stable`, `state`, `scale_online`, `scale_calibrated`, `current_inspection`.
  - `state_change`: Khi chuyển trạng thái `IDLE -> STABILIZING -> INSPECTING -> CHECKOUT`.
  - `inspection_result`: Ngay khi YOLO26n NCNN hoàn tất phân tích khung hình.
  - `receipt_committed`: Khi phiếu nhập kho được lưu vào SQLite.

## 2. REST API Endpoints

### Vận hành trạm (`/api/station`)
- `GET /api/station/state` — Lấy trạng thái hiện tại của trạm.
- `POST /api/station/tare` — Trừ bì đưa cân về `0.0g`.
- `POST /api/station/inspect` — Kích hoạt chụp ảnh & suy luận AI ngay lập tức.
- `POST /api/station/commit` — Chốt đơn / Lưu phiếu nhập kho vào SQLite.
- `POST /api/station/override-food` — Đổi loại thực phẩm (`{"class_name": "Beef"}`) và tính lại dinh dưỡng.
- `POST /api/station/auto-commit` — Bật/tắt tự động lưu phiếu (`{"enabled": true}`).
- `POST /api/station/simulate/weight` — Giả lập cân nặng (chỉ khi `MOCK_HARDWARE=True`).
- `POST /api/station/simulate/ai` — Giả lập nhãn & chất lượng AI (chỉ khi `MOCK_HARDWARE=True`).

### Phần cứng & Hiệu chuẩn (`/api/hardware`)
- `GET /api/hardware/status` — Kiểm tra trạng thái tổng thể Pi 4, Camera, HX711, LCD, AI NCNN.
- `POST /api/hardware/calibrate/tare` — Bước 1 hiệu chuẩn: lấy điểm 0 (21 mẫu).
- `POST /api/hardware/calibrate/measure` — Bước 2 hiệu chuẩn: đo vật chuẩn (`{"known_weight_g": 500}`) và lưu `hardware/calibration.json`.
- `POST /api/hardware/calibrate/invert` — Đảo dấu `scale_ratio`.
- `POST /api/hardware/lcd/test` — Gửi text kiểm tra ra màn hình LCD 16×2.

### Thực phẩm, Lịch sử & Báo cáo (`/api/foods`, `/api/logs`, `/api/reports`)
- `GET /api/foods` — Bảng thành phần dinh dưỡng 64 lớp YOLO26n.
- `GET /api/foods/calculate?class_name=Pork&weight_gram=250` — Quy đổi nhanh dinh dưỡng.
- `PUT /api/foods/{food_id}` — Chỉnh sửa thông số dinh dưỡng chuẩn per 100g.
- `GET /api/logs` — Lịch sử phiếu nhập kho (lọc `date_from`, `date_to`, `quality_status`).
- `GET /api/analytics?days=14` — KPI & chuỗi thống kê theo ngày.
- `GET /api/reports/export.csv` — Tải báo cáo CSV (UTF-8 BOM).
- `GET /api/reports/export.xlsx` — Tải báo cáo Excel `.xlsx`.
