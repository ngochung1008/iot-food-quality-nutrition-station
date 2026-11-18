# SƠ ĐỒ ĐẤU NỐI CHÂN GPIO RASPBERRY PI 4

Tài liệu mô tả chuẩn kết nối phần cứng cho **Trạm tiếp nhận, kiểm định chất lượng & định lượng dinh dưỡng thực phẩm**.

## 1. Loadcell 5kg + Module ADC 24-bit HX711

| Chân HX711 | Chân vật lý Pi 4 (Board) | Chân BCM (GPIO) | Lưu ý kỹ thuật |
| :--- | :--- | :--- | :--- |
| **VCC** | Pin 1 (`3.3V`) | `3.3V` | **Bắt buộc dùng 3.3V** để bảo vệ chân GPIO Pi 4 |
| **GND** | Pin 6 | `GND` | Mass chung |
| **DT (DOUT)** | Pin 29 | **GPIO 5** | Dữ liệu 24-bit (`HX711_DT_PIN=5`) |
| **SCK (PD_SCK)** | Pin 31 | **GPIO 6** | Xung nhịp đọc & Gain 128 (`HX711_SCK_PIN=6`) |

**Đấu nối Loadcell 4 dây vào mạch HX711:**
- Dây Đỏ → `E+`
- Dây Đen → `E-`
- Dây Trắng → `A-`
- Dây Xanh lá → `A+`

## 2. Màn hình LCD 16×2 I2C (Module PCF8574)

| Chân PCF8574 | Chân vật lý Pi 4 (Board) | Chân BCM (GPIO) | Chức năng |
| :--- | :--- | :--- | :--- |
| **GND** | Pin 9 | `GND` | Mass chung |
| **VCC** | Pin 2 hoặc Pin 4 | `5V` | Cấp nguồn đèn nền LCD |
| **SDA** | Pin 3 | **GPIO 2** (`I2C1 SDA`) | Tuyến dữ liệu I2C |
| **SCL** | Pin 5 | **GPIO 3** (`I2C1 SCL`) | Tuyến xung nhịp I2C |

- Địa chỉ I2C mặc định: `0x27` (hoặc `0x3F`). Kiểm tra trên Pi 4 bằng: `sudo i2cdetect -y 1`.

## 3. USB Camera (UVC Webcam)
- Cắm vào cổng **USB 3.0** (màu xanh dương) trên Raspberry Pi 4.
- Hệ thống tự nhận `/dev/video0` với `CAP_V4L2`, định dạng `MJPG`, `640×480 @ 30FPS`, `BUFFERSIZE=1`.
