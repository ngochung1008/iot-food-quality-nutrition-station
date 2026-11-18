#!/bin/bash
# ==============================================================================
# Script cài đặt nhanh môi trường trên Raspberry Pi 4 (Raspberry Pi OS 64-bit)
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo ">>> Cài đặt dự án tại: $PROJECT_DIR"

echo ">>> [1/5] Cập nhật APT và cài các gói tối ưu ARM (OpenCV, NumPy, GPIO, I2C)..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-opencv python3-numpy \
    python3-rpi.gpio python3-smbus i2c-tools \
    git curl

echo ">>> [2/5] Bật giao tiếp I2C (nếu chưa bật)..."
if command -v raspi-config &> /dev/null; then
    sudo raspi-config nonint do_i2c 0 || true
fi

echo ">>> [3/5] Cài đặt thư viện Python cho Raspberry Pi 4 (bao gồm NCNN & RPLCD)..."
cd "$PROJECT_DIR"
pip3 install -r requirements-pi.txt --break-system-packages

echo ">>> [4/5] Tạo file .env thực tế nếu chưa có..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    sed -i 's/MOCK_HARDWARE=True/MOCK_HARDWARE=False/' "$PROJECT_DIR/.env"
    echo ">>> Đã tạo .env với MOCK_HARDWARE=False"
fi

echo ">>> [5/5] Cấp quyền chạy cho scripts..."
chmod +x "$PROJECT_DIR"/scripts/*.sh

echo "=============================================================================="
echo "CÀI ĐẶT HOÀN TẤT!"
echo "1. Kiểm tra địa chỉ LCD I2C: sudo i2cdetect -y 1"
echo "2. Kiểm tra phần cứng     : python3 tests/test_hardware.py"
echo "3. Hiệu chuẩn cân CLI     : python3 scripts/calibrate_cli.py"
echo "4. Chạy server FastAPI    : python3 -m backend.main"
echo "5. Hoặc cài dịch vụ systemd: sudo cp scripts/smart-scale.service /etc/systemd/system/"
echo "=============================================================================="
