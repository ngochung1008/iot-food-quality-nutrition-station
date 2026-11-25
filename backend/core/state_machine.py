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
        self.active_order_id: str | None = None
        self.current_inspection: dict[str, Any] | None = None
        self.last_committed_receipt: dict[str, Any] | None = None
        self._session_committed: bool = False
        self._below_idle_count: int = 0
        self._last_lcd_state: str = ""
        self._last_lcd_weight: float = -999.0
        self._last_lcd_update_ts: float = 0.0
        self._last_lcd_batch: str = ""

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self.on_event(event_type, payload)
        except Exception as exc:
            logger.debug(f"[STATE] Lỗi emit {event_type}: {exc}")

    def snapshot(self) -> dict[str, Any]:
        """Ảnh chụp trạng thái đầy đủ để đẩy khi kết nối/đổi trạng thái hoặc GET /api/station/state."""
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
                "active_order_id": self.active_order_id,
                "current_inspection": self.current_inspection,
                "latest_inspection": self.current_inspection,
                "last_committed_receipt": self.last_committed_receipt,
                "ts": time.time(),
            }

    def telemetry_snapshot(self) -> dict[str, Any]:
        """Gói telemetry gọn nhẹ ở tần số 10Hz qua WebSocket (không gửi kèm inspection/bbox nặng)."""
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
                "active_order_id": self.active_order_id,
                "ts": time.time(),
            }

    def set_auto_commit(self, enabled: bool) -> bool:
        with self._lock:
            self.auto_commit = bool(enabled)
            return self.auto_commit

    def set_active_order(self, order_id: str | None) -> str | None:
        with self._lock:
            self.active_order_id = order_id.strip() if order_id else None
            return self.active_order_id

    def reset_session(self) -> dict[str, Any]:
        """Reset toàn bộ phiên cân về IDLE, xóa kết quả AI và khung bounding box trên camera."""
        with self._lock:
            self.state = StationState.IDLE
            self.current_inspection = None
            self._session_committed = False
            self._below_idle_count = 0
            self.scale.station_state = self.state.value
            if hasattr(self.scale, "reset_stability"):
                self.scale.reset_stability()
            if self.camera:
                self.camera.set_overlay_detections([])
            snap = self.snapshot()
        self._emit("state_change", snap)
        return snap

    def mark_session_committed(self) -> None:
        """Đánh dấu phiên đặt vật hiện tại đã ghi nhận vào phiếu/CSDL đúng 1 lần cho tới khi về IDLE."""
        with self._lock:
            self._session_committed = True

    def reset_after_tare(self) -> dict[str, Any]:
        """Đưa ngay State Machine về IDLE sau khi người dùng bấm Tare / Về 0g."""
        return self.reset_session()

    def _clear_to_idle_locked(self) -> None:
        """Reset sạch phiên cân & xóa bounding box khi đĩa cân trống (< idle_weight_g)."""
        self.state = StationState.IDLE
        self.current_inspection = None
        self._session_committed = False
        self._below_idle_count = 0
        if self.camera:
            self.camera.set_overlay_detections([])

    def update(self) -> str:
        """Cập nhật một chu kỳ State Machine (gọi 10 lần/giây)."""
        w = self.scale.read_filtered_weight()
        need_inspect = False
        cleared_to_idle = False
        with self._lock:
            prev = self.state
            self.scale.station_state = self.state.value
            if self.state == StationState.IDLE:
                if w >= settings.detect_weight_g:
                    self._below_idle_count = 0
                    self.current_inspection = None
                    if self.camera:
                        self.camera.set_overlay_detections([])
                    self.state = StationState.STABILIZING
                    logger.info(f"[STATE] Phát hiện khay thực phẩm ({w:.1f}g) -> STABILIZING")
                elif w < settings.idle_weight_g and self.current_inspection is not None:
                    # Nếu trước đó có kết quả cân vật thật (không phải ép quét thủ công lúc 0g) mà cân đã trống -> xóa sạch
                    if not self.current_inspection.get("manual_empty"):
                        self._below_idle_count += 1
                        if self._below_idle_count >= 3:
                            self._clear_to_idle_locked()
                            cleared_to_idle = True
                    else:
                        self._below_idle_count = 0
                else:
                    self._below_idle_count = 0

            elif self.state == StationState.STABILIZING:
                if w < settings.idle_weight_g:
                    self._below_idle_count += 1
                    # Cần ít nhất 3 lần đọc liên tiếp < 8.0g mới reset về IDLE (chống 1 mẫu nhiễu 0g)
                    if self._below_idle_count >= 3:
                        self._clear_to_idle_locked()
                        cleared_to_idle = True
                        logger.info("[STATE] Cân trống (3 mẫu < 8.0g) -> IDLE (đã xóa kết quả AI & bbox)")
                else:
                    self._below_idle_count = 0
                    if self.scale.is_stable:
                        self.state = StationState.INSPECTING
                        need_inspect = True
                        logger.info(f"[STATE] Trọng lượng ổn định {w:.1f}g -> INSPECTING")

            elif self.state == StationState.INSPECTING:
                if w < settings.idle_weight_g:
                    self._below_idle_count += 1
                    if self._below_idle_count >= 3:
                        self._clear_to_idle_locked()
                        cleared_to_idle = True
                        logger.info("[STATE] Nhấc vật khi đang INSPECTING -> IDLE")

            elif self.state == StationState.CHECKOUT:
                if w < settings.idle_weight_g:
                    self._below_idle_count += 1
                    if self._below_idle_count >= 3:
                        logger.info("[STATE] Đã nhấc thực phẩm khỏi cân (3 mẫu < 8.0g) -> IDLE (đã xóa kết quả AI & bbox)")
                        self._clear_to_idle_locked()
                        cleared_to_idle = True
                else:
                    self._below_idle_count = 0

            self.scale.station_state = self.state.value

        if need_inspect:
            if self.lcd:
                self.lcd.display_station_status(StationState.INSPECTING.value, w)
            self._emit("state_change", self.snapshot())
            try:
                self.run_inspection(weight_gram=w)
            except Exception as exc:
                logger.exception(f"[STATE] Lỗi run_inspection tự động: {exc}")
                with self._lock:
                    if self.scale.read_filtered_weight() < settings.idle_weight_g:
                        self._clear_to_idle_locked()
                    else:
                        self.state = StationState.CHECKOUT
                self._emit("state_change", self.snapshot())

        # Cập nhật LCD 16x2 real-time (ngay khi đổi trạng thái hoặc mỗi 0.5s nếu khối lượng đổi >= 1.0g)
        if self.lcd:
            now_lcd = time.time()
            insp = self.current_inspection
            food_name = insp["nutrition"]["vietnamese_name"] if insp else None
            kcal = insp["nutrition"]["actual"]["energy_kcal"] if insp else None
            qual = insp["quality"]["status"] if insp else None
            conf_val = insp.get("confidence") if insp else None
            batch_code = insp.get("batch_code", "") if insp else ""
            display_state = StationState.CHECKOUT.value if (insp and self.state == StationState.IDLE) else self.state.value

            state_changed = display_state != self._last_lcd_state or batch_code != self._last_lcd_batch
            weight_changed = abs(w - self._last_lcd_weight) >= 1.0 and (now_lcd - self._last_lcd_update_ts) >= 0.5
            if state_changed or weight_changed:
                self.lcd.display_station_status(
                    display_state,
                    w,
                    food_name=food_name,
                    kcal=kcal,
                    quality_status=qual,
                    confidence=conf_val,
                )
                self._last_lcd_state = display_state
                self._last_lcd_batch = batch_code
                self._last_lcd_weight = w
                self._last_lcd_update_ts = now_lcd

        if (self.state != prev or cleared_to_idle) and not need_inspect:
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
            if image_url:
                from backend.services.station_service import station_service

                station_service._cleanup_old_captures(max_files=300)

        detected_class = override_label or prediction.get("detected_class", "Unknown")
        confidence = float(prediction.get("confidence", 0.0))
        if override_label:
            confidence = max(confidence, 0.99)

        quality = assess_food_quality(
            detected_class=detected_class,
            confidence=confidence,
            detections=prediction.get("detections", []),
        )
        if prediction.get("warning"):
            quality["badge_text"] = prediction["warning"]
            quality["recommendation"] = (
                f"{prediction['warning']}. Vui lòng cài đặt thư viện ncnn trên Raspberry Pi 4 "
                "hoặc chọn thực phẩm thủ công."
            )
            quality["alert_level"] = "warning"
        if override_quality in {"FRESH", "WARNING", "REJECTED"}:
            quality["status"] = override_quality
            quality["is_acceptable"] = override_quality != "REJECTED"

        nutrition = calculate_nutrition(detected_class, w)
        batch_code = f"LOT-{time.strftime('%Y%m%d-%H%M%S')}"
        act = nutrition.get("actual", {})

        inspection_result = {
            "batch_code": batch_code,
            "timestamp": utc_now_iso(),
            "local_date": local_today_str(),
            "weight_gram": round(w, 1),
            "weight_g": round(w, 1),
            "detected_class": detected_class,
            "food_name_en": nutrition.get("class_name", detected_class),
            "food_name_vi": nutrition.get("vietnamese_name", detected_class),
            "confidence": round(confidence, 3),
            "confidence_percent": round(confidence * 100.0, 1),
            "unit_price_per_kg": int(nutrition.get("unit_price_per_kg", 0)),
            "total_price_vnd": int(nutrition.get("total_price_vnd", 0)),
            "calories": float(act.get("energy_kcal", 0.0)),
            "protein": float(act.get("protein_g", 0.0)),
            "lipid": float(act.get("fat_g", 0.0)),
            "carb": float(act.get("carbohydrate_g", 0.0)),
            "quality_status": quality.get("status", "FRESH"),
            "bbox": prediction.get("bbox"),
            "inference_time_ms": int(prediction.get("inference_time_ms", 0)),
            "fps": float(prediction.get("fps", 0.0)),
            "strategy": prediction.get("strategy", "ncnn"),
            "warning": prediction.get("warning"),
            "detections": prediction.get("detections", []),
            "image_url": image_url,
            "quality": quality,
            "nutrition": nutrition,
            "committed": False,
            "manual_empty": bool(weight_gram is None and w < settings.idle_weight_g),
        }

        with self._lock:
            self.current_inspection = inspection_result
            if w >= settings.idle_weight_g:
                self.state = StationState.CHECKOUT
            target_order_id = self.active_order_id
            already_committed_in_session = self._session_committed

        if self.lcd:
            self.lcd.display_station_status(
                StationState.CHECKOUT.value,
                w,
                food_name=nutrition.get("vietnamese_name"),
                kcal=act.get("energy_kcal"),
                quality_status=quality.get("status"),
                confidence=confidence,
            )
            self._last_lcd_state = StationState.CHECKOUT.value
            self._last_lcd_batch = batch_code
            self._last_lcd_weight = w
            self._last_lcd_update_ts = time.time()

        # Tự động đối chiếu & cộng dồn nhiều mẻ / TÍCH XANH vào Phiếu Yêu Cầu Nguyên Liệu (chỉ ghi 1 lần/phiên cho tới khi về IDLE)
        auto_checked = False
        allow_auto_record = (not already_committed_in_session) or (override_label is not None and weight_gram is None)
        if allow_auto_record and target_order_id and w >= settings.detect_weight_g and quality.get("status") != "REJECTED":
            from backend.database.crud import get_procurement_order
            from backend.services.station_service import station_service

            order = get_procurement_order(target_order_id)
            if order and order.get("status") in {"PENDING", "IN_PROGRESS"}:
                matched_item = next(
                    (
                        it
                        for it in order["items"]
                        if it["status"] != "COMPLETED"
                        and (
                            it["status"] in {"PENDING", "PARTIAL"}
                            or float(it.get("actual_gram") or 0.0) < float(it.get("min_acceptable_gram") or 0.0)
                        )
                        and it["class_name"].lower() == nutrition["class_name"].lower()
                    ),
                    None,
                )
                if matched_item is not None:
                    try:
                        station_service.commit_current_inspection(
                            order_id=target_order_id,
                            order_item_id=matched_item["id"],
                            confirmed_by="Trạm cân AI (Tự động đối chiếu)",
                            note="Tự động đối chiếu & cộng dồn tại trạm",
                            accumulate=True,
                            allow_partial=True,
                        )
                        auto_checked = True
                        with self._lock:
                            self._session_committed = True
                    except Exception as exc:
                        logger.warning(f"[STATE] Auto đối chiếu bỏ qua: {exc}")

        if allow_auto_record and not auto_checked and self.auto_commit and w >= settings.idle_weight_g:
            from backend.services.station_service import station_service

            station_service.commit_current_inspection(note="Tự động lưu khi cân ổn định", accumulate=False)
            with self._lock:
                self._session_committed = True

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
