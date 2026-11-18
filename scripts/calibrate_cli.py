#!/usr/bin/env python3
"""Công cụ hiệu chuẩn Loadcell HX711 qua dòng lệnh (CLI) trên Raspberry Pi 4.

Kế thừa quy trình từ IOT_CK/calibration.py nhưng lưu trực tiếp vào hardware/calibration.json.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.core.config import settings
from hardware.loadcell import LoadcellManager


def main() -> None:
    print("=" * 68)
    print("   HIỆU CHUẨN CẢM BIẾN TRỌNG LƯỢNG LOADCELL + HX711 (CLI)")
    print("=" * 68)
    scale = LoadcellManager()
    print(f"+ File cấu hình  : {settings.calibration_file}")
    print(f"+ Chế độ Mock    : {settings.mock_hardware}")
    print(f"+ Hệ số hiện tại : {scale.scale_ratio:.4f}")

    input("\n[Bước 1] Đảm bảo đĩa cân TRỐNG HOÀN TOÀN. Nhấn Enter để Tare...")
    if not scale.tare(samples=21):
        print("[LỖI] Tare thất bại!")
        scale.cleanup()
        sys.exit(1)

    raw_w = input("\n[Bước 2] Nhập khối lượng vật mẫu chuẩn (gram, mặc định 500): ").strip()
    known_g = float(raw_w) if raw_w else 500.0
    input(f"Đặt vật mẫu {known_g:.1f}g lên giữa đĩa cân rồi nhấn Enter...")

    res = scale.calibrate_with_known_weight(known_g, invert_if_negative=True)
    if not res.get("ok"):
        print(f"[LỖI] {res.get('error')}")
        scale.cleanup()
        sys.exit(1)

    print(f"\n[THÀNH CÔNG] {res['message']}")
    print("Đọc kiểm tra 5 lần:")
    for i in range(1, 6):
        time.sleep(0.2)
        print(f"  Mẫu {i}: {scale.get_grams():.1f} g")

    scale.cleanup()


if __name__ == "__main__":
    main()
