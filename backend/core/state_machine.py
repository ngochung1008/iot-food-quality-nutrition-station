"""State Machine điều phối quy trình cân & kiểm định tự động: IDLE -> STABILIZING -> INSPECTING -> CHECKOUT."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from backend.core.config import settings
from backend.core.constants import StationState
from backend.database.crud import local_today_str, utc_now_iso
from backend.services.nutrition_service import calculate_nutrition
from backend.services.quality_service import assess_food_quality

logger = logging.getLogger("nutrition_station.state_machine")


class NutritionStationStateMachine:
    """Máy trạng thái trạm cân kiểm định thực phẩm & dinh dưỡng."""

    def __init__(
        self,
        scale,
        camera,
        detector,
        lcd,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.scale = scale
        self.camera = camera
        self.detector = detector
        self.lcd = lcd
        self.on_event = on_event or (lambda *_: None)

        self._lock = threading.RLock()
        self.state: StationState = StationState.IDLE
        self.auto_commit: bool = False
        self.current_inspection: dict[str, Any] | None = None
        self.last_committed_receipt: dict[str, Any] | None = None

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self.on_event(event_type, payload)
        except Exception as exc:
            logger.debug(f"[STATE] Lỗi emit {event_type}: {exc}")

    def snapshot(self) -> dict[str, Any]:
        """Ảnh chụp trạng thái hiện tại để đẩy qua WebSocket hoặc GET /api/station/state."""
        with self._lock:
            weight_g = round(abs(float(self.scale.current_weight)), 1)
            return {
                "station_id": settings.station_id,
                "station_name": settings.station_name,
                "mock_hardware": settings.mock_hardware,
                "state": self.state.value,
                "weight_gram": weight_g,
                "is_stable": bool(self.scale.is_stable),
                "scale_online": bool(self.scale.scale_online),
                "scale_calibrated": bool(self.scale.calibrated),
                "auto_commit": self.auto_commit,
                "current_inspection": self.current_inspection,
                "last_committed_receipt": self.last_committed_receipt,
                "ts": time.time(),
            }

    def set_auto_commit(self, enabled: bool) -> bool:
        with self._lock:
            self.auto_commit = bool(enabled)
            return self.auto_commit

    def update(self) -> str:
        """Cập nhật một chu kỳ State Machine (gọi 10 lần/giây)."""
        w = self.scale.read_filtered_weight()
        with self._lock:
            prev = self.state
            if self.state == StationState.IDLE:
                if w >= settings.detect_weight_g:
                    self.state = StationState.STABILIZING
                    logger.info(f"[STATE] Phát hiện khay thực phẩm ({w:.1f}g) -> STABILIZING")

            elif self.state == StationState.STABILIZING:
                if w < settings.idle_weight_g:
                    self.state = StationState.IDLE
                elif self.scale.is_stable:
                    self.state = StationState.INSPECTING
                    logger.info(f"[STATE] Trọng lượng ổn định {w:.1f}g -> INSPECTING")

            elif self.state == StationState.INSPECTING:
                # Giải phóng lock tạm khi chạy inference AI để không nghẽn snapshot
                pass

            elif self.state == StationState.CHECKOUT:
                if w < settings.idle_weight_g:
                    logger.info("[STATE] Đã nhấc thực phẩm khỏi cân -> IDLE")
                    self.current_inspection = None
                    self.state = StationState.IDLE
                    self.camera.set_overlay_detections([])

        if self.state == StationState.INSPECTING:
            self.run_inspection(weight_gram=w)

        # Cập nhật LCD 16x2 (chỉ ghi I2C khi chuỗi đổi nhờ dirty-check)
        if self.lcd:
            insp = self.current_inspection
            food_name = insp["nutrition"]["vietnamese_name"] if insp else None
            kcal = insp["nutrition"]["actual"]["energy_kcal"] if insp else None
            qual = insp["quality"]["status"] if insp else None
            self.lcd.display_station_status(self.state.value, w, food_name=food_name, kcal=kcal, quality_status=qual)

        if self.state != prev:
            self._emit("state_change", self.snapshot())

        return self.state.value

    def run_inspection(
        self,
        weight_gram: float | None = None,
        override_label: str | None = None,
        override_quality: str | None = None,
    ) -> dict[str, Any]:
        """Chụp khung hình camera, chạy YOLO26n NCNN và tính toán dinh dưỡng."""
        w = float(weight_gram if weight_gram is not None else self.scale.read_filtered_weight())
        frame = self.camera.get_frame()

        if frame is None:
            prediction = {
                "detected_class": override_label or "Unknown",
                "quality_status": "WARNING",
                "confidence": 0.0,
                "inference_time_ms": 0,
                "fps": 0.0,
                "detections": [],
                "strategy": "no-frame",
            }
            image_url = None
        else:
            prediction = self.detector.predict(frame, w)
            annotated = prediction.pop("annotated_frame", frame)
            self.camera.set_overlay_detections(prediction.get("detections", []))
            image_url = self.camera.save_capture(annotated, prefix="inspect")

        detected_class = override_label or prediction.get("detected_class", "Unknown")
        confidence = float(prediction.get("confidence", 0.0))
        if override_label:
            confidence = max(confidence, 0.99)

        quality = assess_food_quality(
            detected_class=detected_class,
            confidence=confidence,
            detections=prediction.get("detections", []),
        )
        if override_quality in {"FRESH", "WARNING", "REJECTED"}:
            quality["status"] = override_quality
            quality["is_acceptable"] = override_quality != "REJECTED"

        nutrition = calculate_nutrition(detected_class, w)
        batch_code = f"LOT-{time.strftime('%Y%m%d-%H%M%S')}"

        inspection_result = {
            "batch_code": batch_code,
            "timestamp": utc_now_iso(),
            "local_date": local_today_str(),
            "weight_gram": round(w, 1),
            "detected_class": detected_class,
            "confidence": round(confidence, 3),
            "inference_time_ms": int(prediction.get("inference_time_ms", 0)),
            "fps": float(prediction.get("fps", 0.0)),
            "strategy": prediction.get("strategy", "ncnn"),
            "detections": prediction.get("detections", []),
            "image_url": image_url,
            "quality": quality,
            "nutrition": nutrition,
            "committed": False,
        }

        with self._lock:
            self.current_inspection = inspection_result
            if w >= settings.idle_weight_g:
                self.state = StationState.CHECKOUT

        if self.auto_commit and w >= settings.idle_weight_g:
            from backend.services.station_service import station_service

            station_service.commit_current_inspection(note="Tự động lưu khi cân ổn định")

        self._emit("inspection_result", self.snapshot())
        return inspection_result

    def override_current_food(self, class_name: str, weight_gram: float | None = None) -> dict[str, Any] | None:
        """Cho phép đầu bếp chọn lại tên thực phẩm trước khi chốt đơn/lưu phiếu."""
        with self._lock:
            w = float(weight_gram if weight_gram is not None else self.scale.current_weight)
            if self.current_inspection is None:
                return self.run_inspection(weight_gram=w, override_label=class_name, override_quality="FRESH")

            nutrition = calculate_nutrition(class_name, w)
            quality = assess_food_quality(class_name, 1.0, [])
            self.current_inspection["detected_class"] = class_name
            self.current_inspection["confidence"] = 1.0
            self.current_inspection["weight_gram"] = round(w, 1)
            self.current_inspection["nutrition"] = nutrition
            self.current_inspection["quality"] = quality
            self.current_inspection["committed"] = False
            snap = self.snapshot()

        self._emit("inspection_result", snap)
        return self.current_inspection
