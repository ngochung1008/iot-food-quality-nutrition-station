"""Dịch vụ điều phối trung tâm (Singleton): kết nối Hardware, AI Engine, State Machine và WebSocket."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from typing import Any

from ai_engine.detector import build_detector
from backend.core.config import settings
from backend.core.state_machine import NutritionStationStateMachine
from backend.database.crud import (
    get_procurement_order,
    init_database,
    insert_intake_log,
    local_today_str,
    mark_procurement_item_completed,
    utc_now_iso,
)
from hardware.camera import CameraManager
from hardware.lcd_display import LCDDisplayManager
from hardware.loadcell import LoadcellManager

logger = logging.getLogger("nutrition_station.services.station")


class WebSocketHub:
    """Quản lý tập kết nối WebSocket bất đồng bộ phát broadcast từ thread nền."""

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add(self, ws: Any) -> None:
        with self._lock:
            self._clients.add(ws)

    def remove(self, ws: Any) -> None:
        with self._lock:
            self._clients.discard(ws)

    def broadcast_sync(self, message: dict[str, Any]) -> None:
        """Gửi bản tin JSON tới tất cả WebSocket clients từ luồng đọc phần cứng."""
        if self._loop is None or self._loop.is_closed():
            return
        with self._lock:
            clients = list(self._clients)
        if not clients:
            return

        async def _send_all() -> None:
            dead = []
            for ws in clients:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._lock:
                    for d in dead:
                        self._clients.discard(d)

        try:
            asyncio.run_coroutine_threadsafe(_send_all(), self._loop)
        except Exception:
            pass


class StationService:
    """Singleton điều phối toàn bộ hoạt động của trạm cân kiểm định thực phẩm."""

    def __init__(self) -> None:
        self._started = False
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self.ws_hub = WebSocketHub()

        self.scale: LoadcellManager | None = None
        self.camera: CameraManager | None = None
        self.lcd: LCDDisplayManager | None = None
        self.detector = None
        self.state_machine: NutritionStationStateMachine | None = None

    def start(self) -> None:
        """Khởi tạo DB, phần cứng, AI và chạy vòng lặp giám sát 10Hz."""
        if self._started:
            return
        init_database()

        self.scale = LoadcellManager()
        self.camera = CameraManager()
        self.lcd = LCDDisplayManager()
        self.detector = build_detector()
        self.camera.start()

        self.state_machine = NutritionStationStateMachine(
            scale=self.scale,
            camera=self.camera,
            detector=self.detector,
            lcd=self.lcd,
            on_event=self._on_station_event,
        )

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="station-orchestrator",
            daemon=True,
        )
        self._worker_thread.start()
        self._started = True
        logger.info(
            f"[STATION] Khởi động hoàn tất (MOCK_HARDWARE={settings.mock_hardware}, AI={self.detector.backend})"
        )

    def stop(self) -> None:
        """Dừng sạch luồng nền và giải phóng phần cứng khi tắt server."""
        if not self._started:
            return
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)
        if self.camera:
            self.camera.stop()
        if self.scale:
            self.scale.cleanup()
        self._started = False
        logger.info("[STATION] Đã dừng hệ thống và giải phóng phần cứng.")

    def _on_station_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.ws_hub.broadcast_sync({"event": event_type, "data": payload})

    def _run_loop(self) -> None:
        interval = 1.0 / max(1, settings.weight_sample_hz)
        while not self._stop_event.is_set():
            started = time.time()
            try:
                if self.state_machine is not None:
                    self.state_machine.update()
                    self.ws_hub.broadcast_sync({
                        "event": "telemetry",
                        "data": self.state_machine.snapshot(),
                    })
            except Exception as exc:
                logger.exception(f"[STATION] Lỗi trong vòng lặp điều phối: {exc}")
            elapsed = time.time() - started
            time.sleep(max(0.02, interval - elapsed))

    def get_hardware_diagnostics(self) -> dict[str, Any]:
        """Tổng hợp trạng thái Raspberry Pi 4, Camera, HX711, LCD và AI NCNN."""
        assert self.scale and self.camera and self.lcd and self.detector
        cam_st = self.camera.get_status()
        hx_st = self.scale.get_status()
        lcd_st = self.lcd.get_status()

        ai_ready = bool(self.detector.is_ready)
        ai_st = {
            "status": "PASS" if ai_ready else "PASS (MOCK)" if settings.mock_hardware else "WARN",
            "strategy": getattr(self.detector, "name", "ncnn"),
            "backend": getattr(self.detector, "backend", "mock"),
            "is_ready": ai_ready,
            "classes_count": getattr(self.detector, "num_classes", 64),
            "input_size": settings.ai_input_size,
            "message": (
                f"YOLO26n NCNN sẵn sàng ({getattr(self.detector, 'backend', '').upper()})"
                if ai_ready
                else "Chưa cài runtime ncnn -> chạy Mock AI dự phòng"
            ),
            "files": {
                "param_exists": settings.ncnn_param_path.exists(),
                "bin_exists": settings.ncnn_bin_path.exists(),
                "metadata_exists": settings.ncnn_metadata_path.exists(),
                "model_dir": str(settings.model_dir),
            },
        }

        if settings.mock_hardware:
            overall = "PASS (MOCK)"
        else:
            ok_all = (
                cam_st["status"] == "PASS"
                and hx_st["status"] == "PASS"
                and lcd_st["status"] == "PASS"
            )
            overall = "PASS" if ok_all else "DEGRADED"

        return {
            "overall": overall,
            "mock_hardware": settings.mock_hardware,
            "station_id": settings.station_id,
            "station_name": settings.station_name,
            "camera": cam_st,
            "hx711": hx_st,
            "lcd": lcd_st,
            "ai": ai_st,
            "timestamp": time.time(),
        }

    def commit_current_inspection(
        self,
        override_class: str | None = None,
        quality_override: str | None = None,
        note: str = "",
        confirmed_by: str = "Nhân viên bếp",
        order_id: str | None = None,
        order_item_id: str | None = None,
    ) -> dict[str, Any]:
        """Chốt đơn / Lưu phiếu tiếp nhận vào SQLite (hỗ trợ đối chiếu Phiếu Yêu Cầu Nguyên Liệu)."""
        assert self.state_machine and self.scale

        if override_class:
            self.state_machine.override_current_food(override_class)

        insp = self.state_machine.current_inspection
        if insp is None:
            insp = self.state_machine.run_inspection(
                weight_gram=self.scale.read_filtered_weight(),
                override_label=override_class,
                override_quality=quality_override,
            )

        if insp.get("committed") and not order_item_id:
            return {"ok": True, "already_committed": True, "receipt": self.state_machine.last_committed_receipt}

        if quality_override in {"FRESH", "WARNING", "REJECTED"}:
            insp["quality"]["status"] = quality_override
            insp["quality"]["is_acceptable"] = quality_override != "REJECTED"

        nut = insp["nutrition"]
        act = nut["actual"]
        weight_g = float(insp["weight_gram"])
        quality_st = insp["quality"]["status"]

        # Nếu đang đối chiếu với một dòng nguyên liệu trong Phiếu Yêu Cầu Nguyên Liệu
        updated_order = None
        if order_id and order_item_id:
            order = get_procurement_order(order_id)
            if not order:
                raise ValueError("Không tìm thấy Phiếu yêu cầu nguyên liệu.")
            target_item = next((it for it in order["items"] if it["id"] == order_item_id), None)
            if not target_item:
                raise ValueError("Không tìm thấy nguyên liệu cần đối chiếu trong phiếu.")
            if nut["class_name"].lower() != target_item["class_name"].lower():
                raise ValueError(
                    f"Sai loại thực phẩm: đang cân '{nut['vietnamese_name']}' ({nut['class_name']}) "
                    f"nhưng dòng cần nhập là '{target_item['food_name_vi']}' ({target_item['class_name']})."
                )
            if quality_st == "REJECTED":
                raise ValueError("Thực phẩm bị đánh giá HƯ HỎNG (REJECTED), không thể tích xanh nhập kho.")
            if weight_g < float(target_item["min_acceptable_gram"]):
                raise ValueError(
                    f"Khối lượng chưa đạt tối thiểu 95%: hiện có {weight_g:.1f}g "
                    f"(yêu cầu tối thiểu {target_item['min_acceptable_gram']:.1f}g / {target_item['required_gram']:.1f}g)."
                )

        receipt = {
            "id": f"rec_{uuid.uuid4().hex[:12]}",
            "batch_code": insp["batch_code"],
            "timestamp": utc_now_iso(),
            "local_date": local_today_str(),
            "station_id": settings.station_id,
            "class_name": nut["class_name"],
            "food_name_vi": nut["vietnamese_name"],
            "food_group": nut["food_group"],
            "weight_gram": weight_g,
            "edible_gram": float(nut["edible_gram"]),
            "quality_status": quality_st,
            "confidence": float(insp["confidence"]),
            "inference_time_ms": int(insp["inference_time_ms"]),
            "strategy": insp["strategy"],
            "energy_kcal": float(act["energy_kcal"]),
            "protein_g": float(act["protein_g"]),
            "fat_g": float(act["fat_g"]),
            "carbohydrate_g": float(act["carbohydrate_g"]),
            "fiber_g": float(act["fiber_g"]),
            "calcium_mg": float(act["calcium_mg"]),
            "iron_mg": float(act["iron_mg"]),
            "vitamin_c_mg": float(act["vitamin_c_mg"]),
            "image_url": insp.get("image_url"),
            "note": note,
            "confirmed_by": confirmed_by,
            "order_id": order_id or "",
            "order_item_id": order_item_id or "",
        }

        insert_intake_log(receipt)
        insp["committed"] = True
        self.state_machine.last_committed_receipt = receipt

        if order_id and order_item_id:
            updated_order = mark_procurement_item_completed(
                order_id=order_id,
                item_id=order_item_id,
                actual_gram=weight_g,
                quality_status=quality_st,
                confidence=float(insp["confidence"]),
                checked_by=confirmed_by,
                log_id=receipt["id"],
                image_url=insp.get("image_url"),
            )
            self._on_station_event("order_updated", {"order": updated_order})

        self._on_station_event("receipt_committed", {"receipt": receipt, "snapshot": self.state_machine.snapshot()})
        return {"ok": True, "already_committed": False, "receipt": receipt, "order": updated_order}


station_service = StationService()
