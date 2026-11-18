"""Driver Camera đa luồng (Threaded VideoCapture) chống nghẽn frame cho Raspberry Pi 4 & Windows.

- Khi MOCK_HARDWARE=False: ưu tiên backend CAP_V4L2 (MJPG 640x480 @ 30fps, BUFFERSIZE=1) trên Pi 4
  và tự động kết nối lại mỗi 2 giây nếu rút cắm USB Camera.
- Khi MOCK_HARDWARE=True: dùng MockCameraGenerator sinh khung hình thực phẩm giả lập mượt mà.
- Cho phép chèn overlay bounding box AI mới nhất lên luồng MJPEG trực tiếp mà không làm khựng camera.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.core.config import settings
from tests.mock_hardware import MockCameraGenerator

logger = logging.getLogger("nutrition_station.hardware.camera")


class CameraManager:
    """Singleton quản lý luồng video đa luồng dùng chung cho Web MJPEG và AI Engine."""

    _instance: CameraManager | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> CameraManager:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.mock_mode: bool = settings.mock_hardware
        self.camera_index: int = settings.camera_index
        self.device_path: str = settings.camera_device
        self.width: int = settings.camera_width
        self.height: int = settings.camera_height
        self.fps: int = settings.camera_fps
        self.buffersize: int = settings.camera_buffersize

        self._lock = threading.Lock()
        self._raw_frame: np.ndarray | None = None
        self._jpeg_bytes: bytes | None = None
        self._overlay_detections: list[dict[str, Any]] = []
        self._overlay_ts: float = 0.0

        self._cap: cv2.VideoCapture | None = None
        self.hardware_available: bool = False
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._consecutive_errors: int = 0
        self._reconnect_attempts: int = 0
        self._last_reconnect_time: float = 0.0

        self._mock_cam = MockCameraGenerator(width=self.width, height=self.height)

        if not self.mock_mode:
            self._open_capture()
        else:
            logger.info("[CAMERA] Khởi động ở chế độ MOCK_HARDWARE=True.")

        self._initialized = True

    def _open_capture(self) -> bool:
        """Mở USB Camera thực tế với V4L2 trên Raspberry Pi hoặc mặc định trên PC."""
        self._close_capture()
        candidates: list[int | str] = [self.camera_index]
        if self.device_path and os.name != "nt" and self.device_path not in candidates:
            candidates.append(self.device_path)
        for alt in (0, 1):
            if alt not in candidates:
                candidates.append(alt)

        for src in candidates:
            try:
                cap = None
                if hasattr(cv2, "CAP_V4L2") and os.name != "nt":
                    cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(src)

                if cap is not None and cap.isOpened():
                    try:
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*settings.camera_fourcc))
                    except Exception:
                        pass
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
                    cap.set(cv2.CAP_PROP_FPS, float(self.fps))
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, float(self.buffersize))
                    except Exception:
                        pass

                    ok, test_frame = cap.read()
                    if ok and test_frame is not None and test_frame.size > 0:
                        self._cap = cap
                        self.hardware_available = True
                        self._consecutive_errors = 0
                        logger.info(f"[CAMERA] Đã kết nối Camera nguồn {src} ({self.width}x{self.height}@{self.fps}fps)")
                        return True
                    cap.release()
            except Exception as exc:
                logger.debug(f"[CAMERA] Không mở được nguồn {src}: {exc}")

        self._cap = None
        self.hardware_available = False
        return False

    def _close_capture(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.hardware_available = False

    def start(self) -> None:
        """Khởi động luồng đọc camera nền (Producer thread)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name="camera-producer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Dừng luồng đọc và giải phóng camera."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._close_capture()

    def set_mock_scene(self, food_label: str | None = None, weight_g: float | None = None, is_rotten: bool | None = None) -> None:
        """Cập nhật khung hình giả lập theo loại thực phẩm và khối lượng."""
        self._mock_cam.set_scene(food_label=food_label, weight_g=weight_g, is_rotten=is_rotten)

    def set_overlay_detections(self, detections: list[dict[str, Any]]) -> None:
        """Cập nhật bounding box hiển thị lên luồng video trực tiếp."""
        with self._lock:
            self._overlay_detections = list(detections or [])
            self._overlay_ts = time.time()

    def _draw_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Vẽ bounding box gần nhất (hết hạn sau 3s nếu không có cập nhật mới)."""
        with self._lock:
            dets = list(self._overlay_detections) if (time.time() - self._overlay_ts) < 3.0 else []
        if not dets:
            return frame
        from ai_engine.detector import draw_detections

        return draw_detections(frame, dets)

    def _standby_frame(self, msg: str) -> np.ndarray:
        frame = np.full((self.height, self.width, 3), (24, 28, 34), dtype=np.uint8)
        cv2.putText(frame, "CAMERA STANDBY", (190, self.height // 2 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220, 230, 240), 2)
        cv2.putText(frame, msg, (110, self.height // 2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (120, 180, 255), 2)
        return frame

    def _capture_loop(self) -> None:
        target_delay = 1.0 / max(10, self.fps)
        while self._running:
            started = time.time()
            if self.mock_mode:
                raw_frame = self._mock_cam.render_frame()
            elif self._cap is not None and self.hardware_available:
                ok, raw = self._cap.read()
                if ok and raw is not None and raw.size > 0:
                    self._consecutive_errors = 0
                    raw_frame = raw
                else:
                    self._consecutive_errors += 1
                    if self._consecutive_errors >= 5:
                        logger.warning("[CAMERA] Mất tín hiệu Camera USB, đang thử kết nối lại...")
                        self._close_capture()
                    raw_frame = self._standby_frame("MAT TIN HIEU CAMERA - DANG THU LAI...")
            else:
                now = time.time()
                if now - self._last_reconnect_time > 2.0:
                    self._last_reconnect_time = now
                    self._reconnect_attempts += 1
                    if self._open_capture():
                        self._reconnect_attempts = 0
                        continue
                raw_frame = self._standby_frame("KHONG TIM THAY CAMERA USB (/dev/video0)")

            display_frame = self._draw_overlay(raw_frame)
            ok_enc, buf = cv2.imencode(".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            jpeg_bytes = buf.tobytes() if ok_enc else None

            with self._lock:
                self._raw_frame = raw_frame
                self._jpeg_bytes = jpeg_bytes

            elapsed = time.time() - started
            time.sleep(max(0.005, target_delay - elapsed))

    def get_frame(self) -> np.ndarray | None:
        """Lấy bản sao frame thô mới nhất cho AI Engine suy luận."""
        with self._lock:
            if self._raw_frame is None:
                return None
            return self._raw_frame.copy()

    def mjpeg_bytes(self) -> bytes | None:
        """Lấy JPEG bytes đã nén sẵn để stream /video_feed."""
        with self._lock:
            return self._jpeg_bytes

    def save_capture(self, frame: np.ndarray, prefix: str = "capture") -> str | None:
        """Lưu ảnh chụp kiểm định ra thư mục captures/ và trả về đường dẫn URL."""
        try:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{stamp}.jpg"
            out_path: Path = settings.capture_dir / filename
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_path), frame)
            return f"/captures/{filename}"
        except Exception as exc:
            logger.error(f"[CAMERA] Lỗi lưu ảnh chụp: {exc}")
            return None

    def get_status(self) -> dict[str, Any]:
        """Trả về trạng thái phần cứng Camera cho trang Diagnostics."""
        if self.mock_mode:
            status = "PASS (MOCK)"
            msg = "Camera đang chạy giả lập (MOCK_HARDWARE=True)"
        elif self.hardware_available:
            status = "PASS"
            msg = f"Camera USB hoạt động tốt ({self.width}x{self.height} @ {self.fps}fps)"
        else:
            status = "FAIL"
            msg = f"Không tìm thấy Camera USB tại index {self.camera_index} ({self.device_path})"

        return {
            "status": status,
            "mode": "mock" if self.mock_mode else "real",
            "available": True if self.mock_mode else self.hardware_available,
            "message": msg,
            "details": {
                "index": self.camera_index,
                "device": self.device_path,
                "resolution": f"{self.width}x{self.height}",
                "fps": self.fps,
                "fourcc": settings.camera_fourcc,
                "is_running": self._running,
                "reconnect_attempts": self._reconnect_attempts,
            },
        }
