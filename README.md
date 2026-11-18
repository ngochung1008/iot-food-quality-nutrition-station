# 🥗 Trạm Tiếp Nhận, Kiểm Định Chất Lượng & Định Lượng Dinh Dưỡng Thực Phẩm AI (Raspberry Pi 4)

Hệ thống Edge AI + IoT thương mại phục vụ bếp ăn tập thể: tự động cân trọng lượng qua **Loadcell + HX711**, nhận diện loại thực phẩm và đánh giá chất lượng tươi/hỏng bằng mô hình **YOLO26n (NCNN 64 lớp)** từ bộ dữ liệu *FISH - Food Is Spotted Here*, quy đổi trực tiếp sang thành phần dinh dưỡng chuẩn (**Viện Dinh Dưỡng Quốc Gia VTN_FCT_2007**), hiển thị lên **LCD 16×2 I2C** và **Web Dashboard FastAPI + WebSocket**.

---

## 🏗️ Kiến Trúc Hệ Thống

```text
iot-food-quality-nutrition-station/
├── backend/              # FastAPI REST API + WebSocket + SQLite + Dịch vụ dinh dưỡng & xuất báo cáo
├── frontend/             # Web Dashboard SPA tách biệt hoàn toàn (Live Station, Diagnostics, Reports)
├── ai_engine/            # Wrapper YOLO26n NCNN tối ưu ARM NEON + Ánh xạ dinh dưỡng 64 lớp
├── hardware/             # Driver đa luồng Camera USB, Loadcell HX711 (Median filter), LCD I2C & calibration.json
├── tests/                # Mock hardware cho Windows + Script test phần cứng, test AI FPS & pytest API
├── scripts/              # Cài đặt nhanh trên Pi 4 (setup_pi.sh), Kiosk autostart, Backup DB, Systemd
├── docs/                 # Sơ đồ đấu nối GPIO, Tài liệu API & Hướng dẫn vận hành
├── .env.example          # Mẫu biến môi trường (MOCK_HARDWARE=True/False)
└── requirements*.txt     # Danh sách thư viện chuẩn cho Dev Windows & Production Pi 4
```

---

## 💻 1. Chạy Chế Độ Giả Lập (Mock Mode) Trên Windows

Chế độ `MOCK_HARDWARE=True` cho phép giả lập mượt mà Loadcell HX711, Camera 640×480 và màn hình LCD 16×2 ngay trên máy tính Windows mà không cần cắm Raspberry Pi 4.

### Bước 1: Tạo môi trường & cài đặt thư viện
```powershell
cd iot-food-quality-nutrition-station
copy .env.example .env
# Kiểm tra trong .env đảm bảo có dòng: MOCK_HARDWARE=True

pip install -r requirements-dev.txt
```

### Bước 2: Chạy kiểm thử độc lập AI, Phần cứng Mock & API
```powershell
python tests/test_hardware.py
python tests/test_ai.py
pytest tests/test_api.py -v
```

### Bước 3: Khởi động Backend + Web Dashboard
```powershell
python -m backend.main
```
Mở trình duyệt truy cập: **http://127.0.0.1:8000**
- Trên giao diện **Trạm Vận Hành Chính**, sử dụng thanh **Chế độ Giả Lập** màu vàng phía trên để thử đặt cân (`350g`, `850g`, `1500g`), đổi loại thực phẩm (`Thịt bò`, `Thịt lợn`, `Cá`, `Cà chua`...) và giả lập trạng thái **TƯƠI / HỎNG**.
- Chuyển sang tab **Phần Cứng & Hiệu Chuẩn** để xem sơ đồ kết nối Raspberry Pi 4 trực quan, nội dung LCD 16×2 mô phỏng và thử Wizard hiệu chuẩn cân.
- Chuyển sang tab **Lịch Sử & Báo Cáo** để xem biểu đồ dinh dưỡng theo ngày/tuần, xuất file `.csv` / `.xlsx` và chỉnh sửa bảng dinh dưỡng 64 loại thực phẩm.

---

## 🍓 2. Triển Khai Thực Tế Trên Raspberry Pi 4

### Bước 1: Đấu nối phần cứng
Xem chi tiết sơ đồ chân GPIO tại [docs/HARDWARE_WIRING.md](docs/HARDWARE_WIRING.md):
- **HX711 Loadcell:** `VCC → 3.3V (Pin 1)`, `GND → Pin 6`, `DT → GPIO 5 (Pin 29)`, `SCK → GPIO 6 (Pin 31)`.
- **LCD 16×2 I2C (PCF8574):** `VCC → 5V (Pin 2/4)`, `GND → Pin 9`, `SDA → GPIO 2 (Pin 3)`, `SCL → GPIO 3 (Pin 5)`, địa chỉ `0x27`.
- **USB Camera:** Cắm cổng USB 3.0 (`/dev/video0`).

### Bước 2: Clone mã nguồn và chạy script cài đặt tự động
```bash
git clone <repo-url> ~/iot-food-quality-nutrition-station
cd ~/iot-food-quality-nutrition-station
chmod +x scripts/setup_pi.sh
./scripts/setup_pi.sh
```
Script sẽ tự động:
1. Cài `python3-opencv`, `python3-numpy`, `python3-rpi.gpio`, `python3-smbus`, `i2c-tools` qua `apt`.
2. Bật giao tiếp I2C.
3. Cài đặt `ncnn` (ARM NEON), `RPLCD`, `fastapi`, `uvicorn` từ `requirements-pi.txt`.
4. Tạo `.env` với `MOCK_HARDWARE=False`.

### Bước 3: Kiểm tra phần cứng & Hiệu chuẩn cân lần đầu
```bash
# Quét địa chỉ LCD I2C (thường là 27 hoặc 3f)
sudo i2cdetect -y 1

# Kiểm tra Camera, HX711, LCD, AI NCNN
python3 tests/test_hardware.py
python3 tests/test_ai.py

# Hiệu chuẩn cân bằng dòng lệnh (hoặc hiệu chuẩn trực tiếp trên Web UI)
python3 scripts/calibrate_cli.py
```

### Bước 4: Khởi chạy dịch vụ nền & Kiosk tự động
```bash
sudo cp scripts/smart-scale.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smart-scale.service
sudo systemctl start smart-scale.service

# Xem log thời gian thực:
sudo journalctl -u smart-scale.service -f
```
Truy cập từ màn hình cảm ứng Pi 4 tại `http://localhost:8000` hoặc từ máy tính trong mạng LAN tại `http://<IP-RASPBERRY-PI>:8000`.
