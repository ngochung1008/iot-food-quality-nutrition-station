"""Bộ giả lập phần cứng (Mock Hardware) phục vụ phát triển và kiểm thử trên Windows.

Cho phép chạy đầy đủ Dashboard Web, WebSocket real-time, hiệu chuẩn cân,
luồng Camera MJPEG và LCD 16x2 mà không cần cắm Raspberry Pi 4 hay cảm biến thật.
"""

from __future__ import annotations

import math
import random
import threading
import time
from typing import Any

import cv2
import numpy as np


class MockScaleDriver:
    """Giả lập cảm biến Loadcell + HX711 với dao động vật lý nhẹ khi đặt hàng."""

    def __init__(self, initial_ratio: float = 420.0) -> None:
        self._lock = threading.Lock()
        self.scale_ratio = initial_ratio
        self.offset = 84000.0
        self.target_weight_g = 0.0
        self.current_raw_weight_g = 0.0
        self._last_change_ts = time.time()

    def set_weight(self, grams: float) -> None:
        """Đặt khối lượng giả lập (gram) từ thanh điều khiển Mock trên giao diện."""
        with self._lock:
            self.target_weight_g = max(0.0, float(grams))
            self._last_change_ts = time.time()

    def tare(self) -> float:
        """Trừ bì giả lập về 0.0g."""
        with self._lock:
            self.offset += self.target_weight_g * self.scale_ratio
            self.target_weight_g = 0.0
            self.current_raw_weight_g = 0.0
            return self.offset

    def read_raw_simulated(self) -> float:
        """Trả về giá trị ADC thô mô phỏng có nhiễu nhỏ (0.2g) trong 0.8s đầu rồi ổn định."""
        with self._lock:
            target = self.target_weight_g
            elapsed = time.time() - self._last_change_ts
            ratio = self.scale_ratio
            offset = self.offset

        if target <= 0.1:
            jitter = 0.0
        elif elapsed < 0.8:
            # Mô phỏng dao động tắt dần khi vừa đặt khay thực phẩm lên cân
            jitter = math.sin(elapsed * 18.0) * min(6.0, target * 0.03) + random.uniform(-0.4, 0.4)
        else:
            jitter = random.uniform(-0.15, 0.15)

        grams = max(0.0, target + jitter)
        return offset + grams * ratio

    def read_grams(self) -> float:
        raw = self.read_raw_simulated()
        with self._lock:
            ratio = self.scale_ratio if self.scale_ratio != 0 else 420.0
            grams = max(0.0, (raw - self.offset) / ratio)
            self.current_raw_weight_g = round(grams, 1)
            return self.current_raw_weight_g


class MockCameraGenerator:
    """Sinh khung hình Camera giả lập 640x480 sắc nét hiển thị khay kiểm định thực phẩm."""

    FOOD_COLORS: dict[str, tuple[int, int, int]] = {
        "Apple": (60, 60, 215),
        "Tomato": (55, 70, 230),
        "Pork": (150, 145, 225),
        "Beef": (65, 65, 165),
        "Fish": (200, 185, 155),
        "Carrot": (40, 130, 240),
        "Cabbage": (95, 185, 105),
        "Banana": (60, 215, 240),
        "Egg": (205, 225, 242),
        "Chicken": (140, 180, 220),
        "Watermelon": (75, 145, 55),
    }

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self._lock = threading.Lock()
        self.active_food: str = "Tomato"
        self.active_weight_g: float = 0.0
        self.is_rotten: bool = False

    def set_scene(self, food_label: str | None = None, weight_g: float | None = None, is_rotten: bool | None = None) -> None:
        with self._lock:
            if food_label is not None:
                self.active_food = food_label
            if weight_g is not None:
                self.active_weight_g = max(0.0, float(weight_g))
            if is_rotten is not None:
                self.is_rotten = bool(is_rotten)

    def render_frame(self) -> np.ndarray:
        """Vẽ khung hình bàn cân + thực phẩm giả lập theo trạng thái hiện tại."""
        with self._lock:
            food = self.active_food
            weight = self.active_weight_g
            rotten = self.is_rotten

        frame = np.full((self.height, self.width, 3), (242, 245, 248), dtype=np.uint8)

        # Vẽ bề mặt bàn cân inox bếp ăn
        cv2.rectangle(frame, (50, 60), (self.width - 50, self.height - 50), (218, 224, 230), -1)
        cv2.rectangle(frame, (50, 60), (self.width - 50, self.height - 50), (140, 152, 165), 3)

        # Vòng định vị khay cân ở tâm
        cx, cy = self.width // 2, self.height // 2 + 10
        cv2.circle(frame, (cx, cy), 135, (185, 195, 205), 2)

        # Nếu có vật trên cân (>= 5g) thì vẽ hình ảnh thực phẩm giả lập
        if weight >= 5.0:
            base_color = self.FOOD_COLORS.get(food, (80, 170, 95))
            if rotten:
                # Đổi sắc thái sẫm màu + đốm nâu mô phỏng thực phẩm hư hỏng
                base_color = (55, 72, 92)
            radius = int(min(105, max(45, 45 + weight * 0.06)))
            cv2.circle(frame, (cx, cy), radius, base_color, -1)
            cv2.circle(frame, (cx, cy), radius, (45, 55, 65), 2)
            # Highlight 3D nhẹ
            cv2.circle(frame, (cx - radius // 3, cy - radius // 3), max(8, radius // 5), (245, 245, 245), -1)
            if rotten:
                cv2.circle(frame, (cx + 15, cy + 12), 18, (35, 42, 55), -1)
                cv2.circle(frame, (cx - 22, cy + 20), 12, (30, 38, 50), -1)

            cv2.putText(
                frame,
                f"SAMPLE: {food.upper()} ({weight:.0f}g)",
                (cx - 125, cy + radius + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (40, 50, 60),
                2,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                frame,
                "TRAY EMPTY - PLACE FOOD ON SCALE",
                (cx - 175, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (110, 120, 130),
                2,
                cv2.LINE_AA,
            )

        # Thanh HUD trên cùng của camera mock
        cv2.rectangle(frame, (0, 0), (self.width, 40), (24, 34, 48), -1)
        ts_str = time.strftime("%H:%M:%S")
        cv2.putText(
            frame,
            f"MOCK CAMERA (640x480) | {ts_str} | FOOD: {food}",
            (16, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (225, 240, 255),
            1,
            cv2.LINE_AA,
        )
        return frame


class MockLCDDriver:
    """Giả lập màn hình LCD 16x2 I2C lưu 2 dòng hiển thị gần nhất."""

    def __init__(self, cols: int = 16, rows: int = 2) -> None:
        self.cols = cols
        self.rows = rows
        self._lock = threading.Lock()
        self.line1 = "STATION READY   "[:cols]
        self.line2 = "0.0g - SAN SANG "[:cols]
        self.history: list[dict[str, Any]] = []

    def write(self, line1: str, line2: str) -> None:
        with self._lock:
            self.line1 = line1[: self.cols].ljust(self.cols)
            self.line2 = line2[: self.cols].ljust(self.cols)
            self.history.append({"ts": time.time(), "line1": self.line1, "line2": self.line2})
            if len(self.history) > 20:
                self.history.pop(0)

    def read(self) -> tuple[str, str]:
        with self._lock:
            return self.line1, self.line2
