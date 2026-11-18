"""Endpoints kiểm định phần cứng, sơ đồ GPIO và hiệu chuẩn cân HX711 trực tiếp từ Web."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.security import ROLE_ADMIN, require_roles, verify_admin_pin
from backend.services.station_service import station_service

router = APIRouter(prefix="/api/hardware", tags=["Hardware & Calibration"])


class CalibrateMeasureRequest(BaseModel):
    known_weight_g: float = Field(..., gt=0.0, le=20000.0)
    invert_if_negative: bool = True


class LcdTestRequest(BaseModel):
    line1: str = "KIEM TRA LCD OK"
    line2: str = "RASPBERRY PI 4"


@router.get("/status")
def hardware_status():
    """Trả về trạng thái chi tiết Camera, HX711, LCD I2C và NCNN AI."""
    return station_service.get_hardware_diagnostics()


@router.post("/calibrate/tare", dependencies=[Depends(require_roles(ROLE_ADMIN)), Depends(verify_admin_pin)])
def calibrate_step_tare():
    """Bước 1 hiệu chuẩn trên Web: Đảm bảo đĩa cân trống và lấy điểm 0 (Tare)."""
    ok = station_service.scale.tare(samples=21)
    if not ok:
        raise HTTPException(status_code=503, detail=station_service.scale.last_error or "Tare thất bại.")
    return {
        "ok": True,
        "offset": round(station_service.scale.offset, 1),
        "message": "Đã lấy điểm 0 (Tare) thành công. Hãy đặt vật mẫu chuẩn lên cân cho Bước 2.",
    }


@router.post("/calibrate/measure", dependencies=[Depends(require_roles(ROLE_ADMIN)), Depends(verify_admin_pin)])
def calibrate_step_measure(body: CalibrateMeasureRequest):
    """Bước 2 hiệu chuẩn trên Web: Đo vật chuẩn đã biết khối lượng và lưu calibration.json."""
    res = station_service.scale.calibrate_with_known_weight(
        known_weight_g=body.known_weight_g,
        invert_if_negative=body.invert_if_negative,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Hiệu chuẩn thất bại."))
    return res


@router.post("/calibrate/invert", dependencies=[Depends(require_roles(ROLE_ADMIN)), Depends(verify_admin_pin)])
def calibrate_invert_sign():
    """Đảo dấu hệ số scale_ratio nếu chiều lực Loadcell bị ngược."""
    new_ratio = station_service.scale.invert_calibration_sign()
    return {"ok": True, "scale_ratio": round(new_ratio, 4)}


@router.post("/lcd/test")
def test_lcd_display(body: LcdTestRequest):
    """Gửi nội dung kiểm tra trực tiếp ra màn hình LCD 16x2 I2C."""
    station_service.lcd.write_lines(body.line1, body.line2)
    return {"ok": True, "lcd": station_service.lcd.get_status()}
