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
        self._current_load_committed: bool = False
        self._current_load_log_id: str | None = None
        self._active_batch_order_id: str | None = None
        self._active_batch_item_id: str | None = None
        self._active_batch_class: str | None = None
        self._active_batch_weight_g: float = 0.0
        self._below_idle_count: int = 0

    @property
    def _batch_accumulated_in_current_load(self) -> bool:
        return self._current_load_committed
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
            self._current_load_committed = False
            self._current_load_log_id = None
            self._active_batch_order_id = None
            self._active_batch_item_id = None
            self._active_batch_class = None
            self._active_batch_weight_g = 0.0
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
        self._current_load_committed = False
        self._current_load_log_id = None
        self._active_batch_order_id = None
        self._active_batch_item_id = None
        self._active_batch_class = None
        self._active_batch_weight_g = 0.0
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
                    insp_w = float((self.current_inspection or {}).get("weight_gram") or 0.0)
                    if self.current_inspection is not None and abs(w - insp_w) > 5.0:
                        logger.info(
                            f"[STATE] Phát hiện đổi hàng/trọng lượng lệch ±5g khi CHECKOUT ({insp_w:.1f}g -> {w:.1f}g) -> STABILIZING để quét lại"
                        )
                        self.current_inspection = None
                        self._session_committed = False
                        self.state = StationState.STABILIZING
                        if hasattr(self.scale, "reset_stability"):
                            self.scale.reset_stability()
                        if self.camera:
                            self.camera.set_overlay_detections([])

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

        with self._lock:
            ctx_order_id = self.active_order_id
        expected_classes: list[str] = []
        if ctx_order_id:
            from backend.database.crud import get_procurement_order

            ctx_order = get_procurement_order(ctx_order_id)
            if ctx_order and ctx_order.get("status") in {"PENDING", "IN_PROGRESS"}:
                expected_classes = list(
                    dict.fromkeys(
                        it["class_name"]
                        for it in ctx_order.get("items", [])
                        if it.get("status") in {"PENDING", "PARTIAL"}
                    )
                )

        if frame is None:
            prediction = {
                "detected_class": override_label or "Unknown",
                "quality_status": "WARNING",
                "confidence": 0.0,
                "inference_time_ms": 0,
                "fps": 0.0,
                "detections": [],
                "top_candidates": [],
                "strategy": "no-frame",
            }
            image_url = None
        else:
            try:
                prediction = self.detector.predict(frame, w, expected_classes=expected_classes)
            except TypeError:
                prediction = self.detector.predict(frame, w)
            annotated = prediction.pop("annotated_frame", frame)
            self.camera.set_overlay_detections(prediction.get("detections", []))
            image_url = self.camera.save_capture(annotated, prefix="inspect")
            if image_url:
                from backend.services.station_service import station_service

                station_service._cleanup_old_captures(max_files=300)

        raw_ai_class = str(prediction.get("detected_class", "Unknown"))
        raw_ai_conf = float(prediction.get("confidence", 0.0))
        detected_class = override_label or raw_ai_class
        confidence = raw_ai_conf
        if override_label:
            confidence = max(confidence, 0.99)

        quality = assess_food_quality(
            detected_class=detected_class,
            confidence=confidence,
            detections=prediction.get("detections", []),
        )
        if prediction.get("quality_note"):
            quality["badge_text"] = prediction["quality_note"]
            quality["recommendation"] = (
                f"{prediction['quality_note']} - Khớp phiếu yêu cầu ({confidence * 100:.0f}%). "
                "Vui lòng kiểm tra cảm quan và xác nhận thủ công trước khi chốt nhập."
            )
            quality["status"] = "WARNING"
            quality["alert_level"] = "warning"
            quality["is_acceptable"] = True
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
        manual_overridden = bool(override_label and override_label.strip().lower() != raw_ai_class.strip().lower())
        override_note = (
            f"Thủ công xác nhận (AI gốc: {raw_ai_class} {round(raw_ai_conf * 100):.0f}%)"
            if manual_overridden
            else ""
        )

        inspection_result = {
            "batch_code": batch_code,
            "timestamp": utc_now_iso(),
            "local_date": local_today_str(),
            "weight_gram": round(w, 1),
            "weight_g": round(w, 1),
            "detected_class": detected_class,
            "ai_origin_class": raw_ai_class,
            "ai_origin_confidence": round(raw_ai_conf, 3),
            "manual_overridden": manual_overridden,
            "override_note": override_note,
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
            "top_candidates": prediction.get("top_candidates", []),
            "reranked": bool(prediction.get("reranked", False)),
            "image_url": image_url,
            "quality": quality,
            "nutrition": nutrition,
            "committed": False,
            "batch_adjusted": False,
            "manual_empty": bool(weight_gram is None and w < settings.idle_weight_g),
        }

        with self._lock:
            prev_state_before_inspect = self.state
            self.current_inspection = inspection_result
            if w >= settings.idle_weight_g:
                self.state = StationState.CHECKOUT
            target_order_id = self.active_order_id
            already_committed_in_session = self._session_committed
            batch_accumulated = self._current_load_committed
            active_batch_log_id = self._current_load_log_id
            active_batch_order_id = self._active_batch_order_id
            active_batch_item_id = self._active_batch_item_id
            active_batch_class = self._active_batch_class
            active_batch_weight_g = self._active_batch_weight_g

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

        # Chỉ tự động cộng dồn / TÍCH XANH 1 lần cho mỗi lượt đặt vật (tới khi về IDLE);
        # nếu vật chưa được nhấc ra khỏi cân (_batch_accumulated_in_current_load == True) thì chỉ điều chỉnh phần delta_gram.
        auto_checked = False
        if target_order_id and w >= settings.detect_weight_g and quality.get("status") == "FRESH":
            from backend.database.crud import get_procurement_order
            from backend.services.station_service import station_service

            order = get_procurement_order(target_order_id)
            same_active_class = bool(
                active_batch_class and active_batch_class.lower() == nutrition["class_name"].lower()
            )
            if batch_accumulated and same_active_class:
                if (
                    active_batch_log_id
                    and active_batch_order_id == target_order_id
                    and active_batch_item_id
                ):
                    cur_item = next((it for it in (order["items"] if order else []) if it["id"] == active_batch_item_id), None)
                    should_adjust = cur_item is not None and cur_item.get("status") != "COMPLETED"
                    delta_gram = round(round(w, 1) - float(active_batch_weight_g), 1)
                    if should_adjust and abs(delta_gram) >= 0.1:
                        try:
                            station_service.adjust_current_batch_item(
                                log_id=active_batch_log_id,
                                order_id=target_order_id,
                                order_item_id=active_batch_item_id,
                                delta_gram=delta_gram,
                                inspection=inspection_result,
                            )
                            inspection_result["batch_adjusted"] = True
                            with self._lock:
                                self._active_batch_weight_g = round(w, 1)
                        except Exception as exc:
                            logger.warning(f"[STATE] Lỗi điều chỉnh delta_gram mẻ hiện tại: {exc}")
                    else:
                        inspection_result["committed"] = True
                        inspection_result["batch_adjusted"] = True
                auto_checked = True
            elif (not already_committed_in_session) or (override_label is not None and (not batch_accumulated or not same_active_class)):
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
                            commit_res = station_service.commit_current_inspection(
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
                                self._current_load_committed = True
                                self._current_load_log_id = (commit_res.get("receipt") or {}).get("id")
                                self._active_batch_order_id = target_order_id
                                self._active_batch_item_id = matched_item["id"]
                                self._active_batch_class = nutrition["class_name"]
                                self._active_batch_weight_g = round(w, 1)
                        except Exception as exc:
                            logger.warning(f"[STATE] Auto đối chiếu bỏ qua: {exc}")

        if (not batch_accumulated) and (not already_committed_in_session) and not auto_checked and self.auto_commit and w >= settings.idle_weight_g and quality.get("status") == "FRESH":
            from backend.services.station_service import station_service

            commit_res = station_service.commit_current_inspection(note="Tự động lưu khi cân ổn định", accumulate=False)
            with self._lock:
                self._session_committed = True
                self._current_load_committed = True
                self._current_load_log_id = (commit_res.get("receipt") or {}).get("id")

        self._emit("inspection_result", self.snapshot())
        return inspection_result

    def override_current_food(self, class_name: str, weight_gram: float | None = None) -> dict[str, Any] | None:
        """Cho phép đầu bếp chọn lại tên thực phẩm trước khi chốt đơn/lưu phiếu, lưu vết AI gốc."""
        with self._lock:
            w = float(weight_gram if weight_gram is not None else self.scale.current_weight)
            if self.current_inspection is None:
                return self.run_inspection(weight_gram=w, override_label=class_name, override_quality="FRESH")

            orig_cls = self.current_inspection.get("ai_origin_class") or self.current_inspection.get("detected_class", "Unknown")
            orig_conf = float(self.current_inspection.get("ai_origin_confidence") or self.current_inspection.get("confidence", 0.0))
            nutrition = calculate_nutrition(class_name, w)
            quality = assess_food_quality(class_name, 1.0, [])
            act = nutrition.get("actual", {})
            self.current_inspection["ai_origin_class"] = orig_cls
            self.current_inspection["ai_origin_confidence"] = round(orig_conf, 3)
            self.current_inspection["manual_overridden"] = True
            self.current_inspection["override_note"] = (
                f"Thủ công xác nhận (AI gốc: {orig_cls} {round(orig_conf * 100):.0f}%)"
            )
            self.current_inspection["detected_class"] = class_name
            self.current_inspection["food_name_en"] = nutrition.get("class_name", class_name)
            self.current_inspection["food_name_vi"] = nutrition.get("vietnamese_name", class_name)
            self.current_inspection["confidence"] = 1.0
            self.current_inspection["confidence_percent"] = 100.0
            self.current_inspection["weight_gram"] = round(w, 1)
            self.current_inspection["weight_g"] = round(w, 1)
            self.current_inspection["unit_price_per_kg"] = int(nutrition.get("unit_price_per_kg", 0))
            self.current_inspection["total_price_vnd"] = int(nutrition.get("total_price_vnd", 0))
            self.current_inspection["calories"] = float(act.get("energy_kcal", 0.0))
            self.current_inspection["protein"] = float(act.get("protein_g", 0.0))
            self.current_inspection["lipid"] = float(act.get("fat_g", 0.0))
            self.current_inspection["carb"] = float(act.get("carbohydrate_g", 0.0))
            self.current_inspection["quality_status"] = quality.get("status", "FRESH")
            self.current_inspection["nutrition"] = nutrition
            self.current_inspection["quality"] = quality
            self.current_inspection["committed"] = False
            snap = self.snapshot()

        self._emit("inspection_result", snap)
        return self.current_inspection
