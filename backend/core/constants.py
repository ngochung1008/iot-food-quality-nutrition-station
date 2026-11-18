"""Hằng số nghiệp vụ & trạng thái cho Trạm kiểm định thực phẩm & dinh dưỡng."""

from __future__ import annotations

from enum import Enum


class StationState(str, Enum):
    """Các trạng thái hoạt động của bàn cân thông minh."""

    IDLE = "IDLE"                  # Đĩa cân trống (< 10g), sẵn sàng tiếp nhận mẻ mới
    STABILIZING = "STABILIZING"    # Có vật đặt lên (>= 15g), đang chờ dao động tắt
    INSPECTING = "INSPECTING"      # Cân ổn định -> Chụp ảnh AI + Tính dinh dưỡng
    CHECKOUT = "CHECKOUT"          # Đã định lượng & hiển thị kết quả, chờ xác nhận/lấy hàng


class QualityStatus(str, Enum):
    """Phân loại chất lượng đầu vào cho bếp ăn tập thể."""

    FRESH = "FRESH"        # Đạt chuẩn tiếp nhận vào bếp
    WARNING = "WARNING"    # Độ tin cậy thấp hoặc cận đát, cần đầu bếp kiểm tra lại
    REJECTED = "REJECTED"  # Phát hiện hư hỏng / ôi thiu -> Từ chối nhập kho


# Ngưỡng cảnh báo chất lượng AI
CONFIDENCE_HIGH_THRESHOLD = 0.70
CONFIDENCE_LOW_WARNING = 0.50

# Từ khóa nhận diện nhãn hư hỏng nếu có từ model mở rộng
ROTTEN_KEYWORDS = (
    "rotten",
    "spoiled",
    "bad",
    "decay",
    "mold",
    "hong",
    "hu_hong",
    "damaged",
    "bruised",
)

# Ngưỡng tham chiếu khẩu phần bếp ăn tập thể (kcal/ngày để tính % đáp ứng tham khảo)
DAILY_REF_KCAL = 2000.0
DAILY_REF_PROTEIN_G = 60.0
DAILY_REF_FAT_G = 65.0
DAILY_REF_CARB_G = 300.0
