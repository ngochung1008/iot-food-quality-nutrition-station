"""Endpoints vận hành trạm cân: Trạng thái, Tare, Nhận diện AI, Chốt phiếu & Giả lập Mock."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.services.station_service import station_service

router = APIRouter(prefix="/api/station", tags=["Station"])


class InspectRequest(BaseModel):
    override_label: str | None = None
    override_quality: str | None = None


class CommitRequest(BaseModel):
    override_class: str | None = None
    quality_override: str | None = None
    note: str = ""
    confirmed_by: str = "Nhân viên bếp"


class OverrideFoodRequest(BaseModel):
    class_name: str = Field(..., min_length=1)


class AutoCommitRequest(BaseModel):
    enabled: bool


class SimulateWeightRequest(BaseModel):
    weight_gram: float = Field(..., ge=0.0, le=50000.0)


class SimulateAIRequest(BaseModel):
    label: str | None = None
    quality: str | None = None


@router.get("/state")
def get_station_state():
    """Trả về trạng thái thời gian thực hiện tại của trạm cân."""
    return station_service.state_machine.snapshot()


@router.post("/tare")
def tare_scale():
    """Trừ bì (Tare) đưa bàn cân về 0.0g."""
    ok = station_service.scale.tare(samples=21)
    if not ok:
        raise HTTPException(status_code=503, detail=station_service.scale.last_error or "Tare thất bại.")
    return {
        "ok": True,
        "weight_gram": float(station_service.scale.current_weight),
        "scale_online": station_service.scale.scale_online,
    }


@router.post("/inspect")
def trigger_inspection(body: InspectRequest | None = None):
    """Kích hoạt chụp ảnh & chạy suy luận AI YOLO26n ngay lập tức."""
    req = body or InspectRequest()
    result = station_service.state_machine.run_inspection(
        override_label=req.override_label,
        override_quality=req.override_quality,
    )
    return {
        "ok": True,
        "inspection": result,
        "snapshot": station_service.state_machine.snapshot(),
    }


@router.post("/commit")
def commit_receipt(body: CommitRequest | None = None):
    """Chốt đơn / Lưu phiếu kiểm định dinh dưỡng vào SQLite."""
    req = body or CommitRequest()
    return station_service.commit_current_inspection(
        override_class=req.override_class,
        quality_override=req.quality_override,
        note=req.note,
        confirmed_by=req.confirmed_by,
    )


@router.post("/override-food")
def override_food(body: OverrideFoodRequest):
    """Cho phép đầu bếp chọn lại loại thực phẩm và tính lại dinh dưỡng theo trọng lượng đang cân."""
    insp = station_service.state_machine.override_current_food(body.class_name)
    if settings.mock_hardware and station_service.camera:
        station_service.camera.set_mock_scene(food_label=body.class_name)
    return {"ok": True, "inspection": insp}


@router.post("/auto-commit")
def toggle_auto_commit(body: AutoCommitRequest):
    """Bật/tắt tự động lưu phiếu ngay khi cân ổn định."""
    enabled = station_service.state_machine.set_auto_commit(body.enabled)
    return {"ok": True, "auto_commit": enabled}


@router.post("/simulate/weight")
def simulate_weight(body: SimulateWeightRequest):
    """Giả lập trọng lượng trên bàn cân khi MOCK_HARDWARE=True."""
    if not settings.mock_hardware:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ giả lập khi MOCK_HARDWARE=True.")
    station_service.scale.set_simulated_weight(body.weight_gram)
    station_service.camera.set_mock_scene(weight_g=body.weight_gram)
    return {"ok": True, "weight_gram": body.weight_gram}


@router.post("/simulate/ai")
def simulate_ai(body: SimulateAIRequest):
    """Giả lập loại thực phẩm và chất lượng tươi/hỏng khi MOCK_HARDWARE=True."""
    if not settings.mock_hardware:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ giả lập khi MOCK_HARDWARE=True.")
    if hasattr(station_service.detector, "force_next"):
        station_service.detector.force_next(label=body.label, quality=body.quality)
    is_rotten = (body.quality or "").upper() == "REJECTED"
    station_service.camera.set_mock_scene(
        food_label=body.label,
        is_rotten=is_rotten if body.quality else None,
    )
    return {"ok": True, "label": body.label, "quality": body.quality}
