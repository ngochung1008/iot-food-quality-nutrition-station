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

    if not detected_class or detected_class == "Unknown":
        return {
            "status": QualityStatus.WARNING.value,
            "is_acceptable": True,
            "badge_text": "Cần kiểm tra cảm quan (Chưa nhận diện rõ)",
            "recommendation": "AI chưa nhận diện chắc chắn loại thực phẩm. Vui lòng kiểm tra cảm quan và chọn đúng tên thực phẩm trước khi lưu phiếu.",
            "alert_level": "warning",
        }

    if confidence < CONFIDENCE_HIGH_THRESHOLD:
        return {
            "status": QualityStatus.WARNING.value,
            "is_acceptable": True,
            "badge_text": "Cần kiểm tra cảm quan (Độ tự tin AI trung bình)",
            "recommendation": f"Độ tin cậy AI {confidence * 100:.0f}%. Cần kiểm tra cảm quan (màu sắc, mùi, độ tươi) và xác nhận thủ công trước khi nhập kho.",
            "alert_level": "warning",
        }

    return {
        "status": QualityStatus.FRESH.value,
        "is_acceptable": True,
        "badge_text": "Đạt chuẩn nhận diện (Chờ/Đạt QA cảm quan)",
        "recommendation": f"Chủng loại '{detected_class}' khớp mẫu chuẩn (độ tin cậy {confidence * 100:.0f}%). Sẵn sàng tiếp nhận sau kiểm tra cảm quan.",
        "alert_level": "success",
    }
