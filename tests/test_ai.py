#!/usr/bin/env python3
"""tests/test_ai.py — Kiểm thử tốc độ FPS, file mô hình YOLO26n NCNN và ánh xạ dinh dưỡng."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai_engine.detector import build_detector, load_metadata_names
from ai_engine.nutrition_mapper import get_nutrition_profile
from backend.core.config import settings
from backend.database.crud import init_database
from backend.services.nutrition_service import calculate_nutrition


def find_sample_images(limit: int = 5) -> list[Path]:
    sample_dir = settings.data_dir / "FISH - Food Is Spotted Here.v2-fish-dataset-v2.yolov8" / "test" / "images"
    if not sample_dir.exists():
        return []
    return sorted(sample_dir.glob("*.jpg"))[:limit]


def run_ai_tests() -> int:
    print("=" * 74)
    print("  KIỂM THỬ MODULE AI YOLO26n (NCNN) & BẢNG DINH DƯỠNG 64 LỚP")
    print("=" * 74)

    # 1. Kiểm tra 3 file model
    print("[1/4] Kiểm tra file NCNN tại:", settings.model_dir)
    for p in (settings.ncnn_param_path, settings.ncnn_bin_path, settings.ncnn_metadata_path):
        print(f"  - {p.name:<18}: {'OK' if p.exists() else 'MISSING'} ({p})")
    if not (settings.ncnn_param_path.exists() and settings.ncnn_bin_path.exists() and settings.ncnn_metadata_path.exists()):
        print("[FAIL] Thiếu file mô hình NCNN!")
        return 1

    # 2. Kiểm tra metadata 64 nhãn & ánh xạ dinh dưỡng
    names = load_metadata_names()
    print(f"\n[2/4] Đã nạp {len(names)} nhãn từ metadata.yaml.")
    missing_nut = [name for name in names.values() if get_nutrition_profile(name) is None]
    print(f"  - Số nhãn thiếu dinh dưỡng: {len(missing_nut)}")
    if missing_nut:
        print(f"  [WARN] Nhãn chưa có trong mapper: {missing_nut}")
        return 1

    # 3. Khởi tạo Detector & Benchmark FPS trên ảnh mẫu
    print("\n[3/4] Khởi tạo AI Detector & đo hiệu năng...")
    detector = build_detector()
    print(f"  - Strategy: {detector.name} | Backend: {detector.backend} | Ready: {detector.is_ready}")

    samples = find_sample_images(limit=5)
    frames = []
    for img_path in samples:
        img = cv2.imread(str(img_path))
        if img is not None:
            frames.append((img_path.name, img))

    if not frames:
        frames = [("synthetic_640x480", np.full((480, 640, 3), 180, dtype=np.uint8))]

    latencies = []
    for fname, frame in frames:
        t0 = time.perf_counter()
        res = detector.predict(frame, weight_gram=500.0)
        ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(ms)
        print(
            f"  - {fname[:32]:<32} -> {res['detected_class']:<14} "
            f"(conf={res['confidence']:.2f}, {ms:.1f} ms, strategy={res['strategy']})"
        )

    avg_ms = sum(latencies) / len(latencies)
    fps = 1000.0 / avg_ms if avg_ms > 0 else 0.0
    print(f"  -> Trung bình: {avg_ms:.1f} ms/ảnh (~{fps:.1f} FPS)")

    # 4. Kiểm tra tính toán dinh dưỡng thực tế
    print("\n[4/4] Kiểm tra quy đổi dinh dưỡng (g -> kcal/protein/fat/carb)...")
    init_database()
    nut = calculate_nutrition("Beef", 250.0)
    print(
        f"  - Beef 250g -> {nut['actual']['energy_kcal']} kcal | "
        f"P={nut['actual']['protein_g']}g | F={nut['actual']['fat_g']}g | C={nut['actual']['carbohydrate_g']}g"
    )
    if not nut["matched"] or nut["actual"]["energy_kcal"] <= 0:
        print("[FAIL] Lỗi tính toán dinh dưỡng!")
        return 1

    print("\n[PASS] Module AI & Dinh dưỡng hoạt động chính xác!")
    return 0


if __name__ == "__main__":
    sys.exit(run_ai_tests())
