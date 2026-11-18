"""Dịch vụ đánh giá chất lượng tươi/hỏng & khuyến nghị tiếp nhận cho bếp ăn tập thể."""

from __future__ import annotations

from typing import Any

from backend.core.constants import CONFIDENCE_HIGH_THRESHOLD, QualityStatus, ROTTEN_KEYWORDS


def assess_food_quality(
    detected_class: str,
    confidence: float,
    detections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Đánh giá lô thực phẩm đạt chuẩn (FRESH), cần kiểm tra (WARNING) hay từ chối (REJECTED)."""
    detections = detections or []
    rotten_found = any(
        any(kw in str(d.get("label", "")).lower() for kw in ROTTEN_KEYWORDS)
        for d in detections
    )
    label_lower = (detected_class or "").lower()
    is_rotten_label = rotten_found or any(kw in label_lower for kw in ROTTEN_KEYWORDS)

    if is_rotten_label:
        return {
            "status": QualityStatus.REJECTED.value,
            "is_acceptable": False,
            "badge_text": "KHÔNG ĐẠT - PHÁT HIỆN HƯ HỎNG",
            "recommendation": "Từ chối nhập kho! Loại bỏ phần thực phẩm dập nát/ôi thiu và kiểm tra lại cả lô.",
            "alert_level": "danger",
        }

    if not detected_class or detected_class == "Unknown" or confidence < 0.35:
        return {
            "status": QualityStatus.WARNING.value,
            "is_acceptable": True,
            "badge_text": "CẦN KIỂM TRA THỦ CÔNG",
            "recommendation": "AI chưa nhận diện chắc chắn loại thực phẩm. Vui lòng chọn đúng tên thực phẩm trước khi lưu phiếu.",
            "alert_level": "warning",
        }

    if confidence < CONFIDENCE_HIGH_THRESHOLD:
        return {
            "status": QualityStatus.WARNING.value,
            "is_acceptable": True,
            "badge_text": "ĐỘ TIN CẬY TRUNG BÌNH",
            "recommendation": f"Độ tin cậy {confidence * 100:.0f}%. Kiểm tra nhanh cảm quan (màu sắc, mùi) trước khi nhập bếp.",
            "alert_level": "warning",
        }

    return {
        "status": QualityStatus.FRESH.value,
        "is_acceptable": True,
        "badge_text": "ĐẠT CHUẨN TƯƠI SẠCH",
        "recommendation": "Thực phẩm đạt chất lượng đầu vào. Sẵn sàng chốt phiếu nhập kho bếp ăn.",
        "alert_level": "success",
    }
