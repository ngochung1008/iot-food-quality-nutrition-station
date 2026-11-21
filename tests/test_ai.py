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

    # 4. Kiểm tra giải mã tensor (68, 3549) & Letterbox 416x416 -> khung hình gốc
    print("\n[4/5] Kiểm tra giải mã tensor YOLO26n NCNN (68, 3549) + Letterbox 416x416...")
    from ai_engine.detector import NCNNYoloDetector

    dec = NCNNYoloDetector()
    test_img = frames[0][1]
    padded, ratio, pad_x, pad_y = dec._letterbox(test_img, 416)
    assert padded.shape == (416, 416, 3), f"Letterbox shape sai: {padded.shape}"

    fake_out = np.zeros((68, 3549), dtype=np.float32)
    # Đặt 1 box giả lập cho lớp 27 (Fish) tại tâm 416x416
    fake_out[0, 100] = 208.0  # cx
    fake_out[1, 100] = 208.0  # cy
    fake_out[2, 100] = 180.0  # w
    fake_out[3, 100] = 120.0  # h
    fake_out[4 + 27, 100] = 0.88  # Fish confidence
    dets = dec._postprocess_yolo(fake_out, test_img.shape[:2], letterbox=(ratio, pad_x, pad_y))
    assert dets and dets[0]["label"] == "Fish" and dets[0]["confidence"] >= 0.85, f"Decode sai: {dets}"
    print(f"  - Giải mã chuẩn xác: {dets[0]['label']} ({dets[0]['confidence']*100:.1f}%) bbox={dets[0]['box']}")

    # 5. Kiểm tra tính toán dinh dưỡng & đơn giá thực tế
    print("\n[5/5] Kiểm tra quy đổi dinh dưỡng (g -> kcal/protein/fat/carb) & đơn giá...")
    init_database()
    nut = calculate_nutrition("Beef", 250.0)
    print(
        f"  - Beef 250g -> {nut['actual']['energy_kcal']} kcal | "
        f"P={nut['actual']['protein_g']}g | F={nut['actual']['fat_g']}g | C={nut['actual']['carbohydrate_g']}g | "
        f"Giá={nut['total_price_vnd']:,} đ ({nut['unit_price_per_kg']:,} đ/kg)"
    )
    if not nut["matched"] or nut["actual"]["energy_kcal"] <= 0 or nut["total_price_vnd"] <= 0:
        print("[FAIL] Lỗi tính toán dinh dưỡng / đơn giá!")
        return 1

    print("\n[PASS] Module AI & Dinh dưỡng hoạt động chính xác!")
    return 0


if __name__ == "__main__":
    sys.exit(run_ai_tests())
