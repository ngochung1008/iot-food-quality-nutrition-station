"""Cấu hình tập trung đọc từ biến môi trường (.env) cho Backend, AI và Phần cứng."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Xác định thư mục gốc dự án (iot-food-quality-nutrition-station/)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Chuyển đổi chuỗi biến môi trường sang kiểu bool an toàn."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_hex(value: str | None, default: int) -> int:
    """Chuyển đổi chuỗi hex (0x27) hoặc thập phân sang số nguyên."""
    if not value:
        return default
    raw = value.strip()
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return default


def _resolve_model_dir() -> Path:
    """Tìm thư mục chứa 3 file mô hình YOLO26n NCNN."""
    candidates = [
        ROOT_DIR / "ai_engine" / "models",
        ROOT_DIR,
    ]
    for folder in candidates:
        if (folder / "model.ncnn.param").exists() and (folder / "model.ncnn.bin").exists():
            return folder
    return ROOT_DIR / "ai_engine" / "models"


def _determine_mock_hardware() -> bool:
    """Xác định chế độ MOCK_HARDWARE (ưu tiên MOCK_HARDWARE, tương thích HARDWARE_MODE)."""
    if "MOCK_HARDWARE" in os.environ:
        return _parse_bool(os.getenv("MOCK_HARDWARE"), default=True)
    hw_mode = os.getenv("HARDWARE_MODE", "").strip().lower()
    if hw_mode in {"mock", "real"}:
        return hw_mode == "mock"
    # Mặc định an toàn trên Windows là True nếu chưa cấu hình .env
    return os.name == "nt"


@dataclass(frozen=True)
class Settings:
    """Cấu hình toàn hệ thống bất biến khi runtime."""

    root_dir: Path = ROOT_DIR
    backend_dir: Path = ROOT_DIR / "backend"
    frontend_dir: Path = ROOT_DIR / "frontend" / "src"
    frontend_public_dir: Path = ROOT_DIR / "frontend" / "public"
    data_dir: Path = ROOT_DIR / "data"
    db_path: Path = ROOT_DIR / "backend" / "data" / "nutrition_station.db"
    capture_dir: Path = ROOT_DIR / "captures"
    calibration_file: Path = ROOT_DIR / "hardware" / "calibration.json"

    # AI NCNN Paths
    model_dir: Path = _resolve_model_dir()
    ncnn_param_path: Path = model_dir / "model.ncnn.param"
    ncnn_bin_path: Path = model_dir / "model.ncnn.bin"
    ncnn_metadata_path: Path = model_dir / "metadata.yaml"
    vtn_fct_path: Path = ROOT_DIR / "data" / "datasets_curated" / "nutrition" / "vtn_fct_2007.json"

    # Chế độ giả lập phần cứng
    mock_hardware: bool = _determine_mock_hardware()
    station_id: str = os.getenv("STATION_ID", "STATION-KITCHEN-01").strip()
    station_name: str = os.getenv("STATION_NAME", "Bếp Ăn Tập Thể - Cổng Tiếp Nhận Số 1").strip()

    # Loadcell HX711 (BCM GPIO)
    hx711_dt_pin: int = int(os.getenv("HX711_DT_PIN", "5"))
    hx711_sck_pin: int = int(os.getenv("HX711_SCK_PIN", "6"))
    hx711_invert_signal: bool = _parse_bool(os.getenv("HX711_INVERT_SIGNAL"), default=True)
    hx711_zero_band_g: float = float(os.getenv("HX711_ZERO_BAND_G", "0.5"))
    hx711_median_samples: int = int(os.getenv("HX711_MEDIAN_SAMPLES", "15"))
    weight_sample_hz: int = int(os.getenv("WEIGHT_SAMPLE_HZ", "10"))

    # State Machine thresholds (ổn định 0.8s với Δm < 2.5g; cần 3 mẫu < 8.0g mới về IDLE)
    idle_weight_g: float = float(os.getenv("IDLE_WEIGHT_G", "8.0"))
    detect_weight_g: float = float(os.getenv("DETECT_WEIGHT_G", "15.0"))
    stability_delta_g: float = float(os.getenv("STABILITY_DELTA_G", "2.5"))
    stability_hold_s: float = float(os.getenv("STABILITY_HOLD_S", "0.8"))

    # LCD I2C PCF8574
    lcd_i2c_address: int = _parse_int_hex(os.getenv("LCD_I2C_ADDRESS"), 0x27)
    lcd_i2c_port: int = int(os.getenv("LCD_I2C_PORT", "1"))
    lcd_cols: int = int(os.getenv("LCD_COLS", "16"))
    lcd_rows: int = int(os.getenv("LCD_ROWS", "2"))

    # Camera USB
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    camera_device: str = os.getenv("CAMERA_DEVICE", "/dev/video0").strip()
    camera_width: int = int(os.getenv("CAMERA_WIDTH", "640"))
    camera_height: int = int(os.getenv("CAMERA_HEIGHT", "480"))
    camera_fps: int = int(os.getenv("CAMERA_FPS", "30"))
    camera_fourcc: str = os.getenv("CAMERA_FOURCC", "MJPG").strip()
    camera_buffersize: int = int(os.getenv("CAMERA_BUFFERSIZE", "1"))

    # AI Engine
    ai_strategy: str = os.getenv("AI_STRATEGY", "auto").strip().lower()
    ai_confidence_threshold: float = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.35"))
    ai_nms_iou_threshold: float = float(os.getenv("AI_NMS_IOU_THRESHOLD", "0.45"))
    ai_input_size: int = int(os.getenv("AI_INPUT_SIZE", "416"))
    ai_num_threads: int = int(os.getenv("AI_NUM_THREADS", "2"))

    # Server & Security
    host: str = os.getenv("HOST", "0.0.0.0").strip()
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = _parse_bool(os.getenv("DEBUG"), default=False)
    cors_origins: str = os.getenv("CORS_ORIGINS", "*").strip()
    admin_pin: str = os.getenv("ADMIN_PIN", "").strip()
    jwt_secret: str = os.getenv("JWT_SECRET", "fresh-kitchen-enterprise-secret-2026").strip()
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    def ensure_dirs(self) -> None:
        """Tạo các thư mục runtime cần thiết nếu chưa tồn tại."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.calibration_file.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
