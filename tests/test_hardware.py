#!/usr/bin/env python3
"""tests/test_hardware.py — Kiểm thử độc lập từng thành phần phần cứng (Loadcell, LCD, Camera, AI).

Kế thừa logic từ IOT_CK/check_hardware.py, tương thích cả chế độ MOCK_HARDWARE=True (Windows)
và MOCK_HARDWARE=False (Raspberry Pi 4 thật).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core.config import settings
from hardware.camera import CameraManager
from hardware.lcd_display import LCDDisplayManager
from hardware.loadcell import LoadcellManager


def run_hardware_checks() -> int:
    print("=" * 74)
    print("  KIỂM THỬ PHẦN CỨNG TRẠM KIỂM ĐỊNH THỰC PHẨM & DINH DƯỠNG (PI 4)")
    print("=" * 74)
    print(f"Chế độ MOCK_HARDWARE = {settings.mock_hardware}")

    # 1. Test Loadcell HX711
    print("\n[1/3] Kiểm tra Loadcell HX711...")
    scale = LoadcellManager()
    if settings.mock_hardware:
        scale.set_simulated_weight(450.0)
        time.sleep(0.25)
    else:
        # Chờ luồng nền HX711 kịp hoàn thành mẫu đọc đầu tiên sau khi tare()
        time.sleep(0.8)
    scale_status = scale.get_status()
    print(f"  -> Trạng thái : {scale_status['status']}")
    print(f"  -> Chi tiết   : {scale_status['message']}")
    print(f"  -> Đo thử     : {scale.read_filtered_weight():.1f} g")

    # 2. Test LCD 16x2 I2C
    print("\n[2/3] Kiểm tra LCD 16x2 I2C (PCF8574)...")
    lcd = LCDDisplayManager()
    lcd.write_lines("TEST HARDWARE", "RPI4 NUTRI OK")
    lcd_status = lcd.get_status()
    print(f"  -> Trạng thái : {lcd_status['status']}")
    print(f"  -> Chi tiết   : {lcd_status['message']}")
    print(f"  -> Line 1/2   : '{lcd_status['details']['line1']}' | '{lcd_status['details']['line2']}'")

    # 3. Test Camera
    print("\n[3/3] Kiểm tra Camera đa luồng...")
    camera = CameraManager()
    camera.start()
    time.sleep(0.3)
    frame = camera.get_frame()
    cam_status = camera.get_status()
    frame_info = f"{frame.shape[1]}x{frame.shape[0]}" if frame is not None else "None"
    print(f"  -> Trạng thái : {cam_status['status']}")
    print(f"  -> Chi tiết   : {cam_status['message']} (Frame={frame_info})")

    camera.stop()
    scale.cleanup()

    ok = (
        "FAIL" not in scale_status["status"]
        and "FAIL" not in lcd_status["status"]
        and "FAIL" not in cam_status["status"]
    )
    print("\n" + "=" * 74)
    print("KẾT LUẬN:", "PASS - Phần cứng sẵn sàng!" if ok else "FAIL - Có thiết bị lỗi!")
    print("=" * 74)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_hardware_checks())
