"""Driver điều khiển màn hình LCD 16x2 giao tiếp I2C (chip PCF8574) trên Raspberry Pi 4.

- Tự động bỏ dấu tiếng Việt (ASCII-safe) và căn vừa đúng 16 ký tự mỗi dòng.
- Cơ chế dirty-check: chỉ ghi I2C khi nội dung thay đổi để giảm tải bus và tránh nhấp nháy.
- Xử lý try-except chặt chẽ khi mất kết nối LCD để không làm sập server.
- Khi MOCK_HARDWARE=True: lưu nội dung vào MockLCDDriver để xem trực tiếp trên Web Diagnostics.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from typing import Any

from backend.core.config import settings
from tests.mock_hardware import MockLCDDriver

logger = logging.getLogger("nutrition_station.hardware.lcd")

try:
    from RPLCD.i2c import CharLCD  # type: ignore

    HAS_RPLCD = True
except ImportError:
    CharLCD = None  # type: ignore
    HAS_RPLCD = False


def strip_vietnamese_diacritics(text: str) -> str:
    """Chuyển tiếng Việt có dấu sang chuỗi ASCII sạch cho LCD 16x2."""
    replacements = str.maketrans(
        "àáảãạăằắẳẵặâầấẩẫậÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ"
        "èéẻẽẹêềếểễệÈÉẺẼẸÊỀẾỂỄỆ"
        "ìíỉĩịÌÍỈĨỊ"
        "òóỏõọôồốổỗộơờớởỡợÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"
        "ùúủũụưừứửữựÙÚỦŨỤƯỪỨỬỮỰ"
        "ỳýỷỹỵỲÝỶỸỴđĐ",
        "aaaaaaaaaaaaaaaaaAAAAAAAAAAAAAAAAA"
        "eeeeeeeeeeeEEEEEEEEEEE"
        "iiiiiIIIII"
        "oooooooooooooooooOOOOOOOOOOOOOOOOO"
        "uuuuuuuuuuuUUUUUUUUUUU"
        "yyyyyYYYYYdD",
    )
    normalized = unicodedata.normalize("NFKD", text.translate(replacements))
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in ascii_only)


def format_lcd_line(text: str, cols: int = 16) -> str:
    """Cắt hoặc đệm khoảng trắng đúng độ rộng LCD."""
    clean = strip_vietnamese_diacritics(str(text))
    return clean[:cols].ljust(cols)


class LCDDisplayManager:
    """Singleton điều khiển LCD 16x2 I2C với tự phục hồi và giả lập Mock."""

    _instance: LCDDisplayManager | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> LCDDisplayManager:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.mock_mode: bool = settings.mock_hardware
        self.address: int = settings.lcd_i2c_address
        self.port: int = settings.lcd_i2c_port
        self.cols: int = settings.lcd_cols
        self.rows: int = settings.lcd_rows

        self._lock = threading.Lock()
        self._lcd = None
        self.hardware_available: bool = False
        self.last_error: str | None = None
        self._last_line1: str = ""
        self._last_line2: str = ""
        self._mock_lcd = MockLCDDriver(cols=self.cols, rows=self.rows)

        if self.mock_mode:
            logger.info("[LCD] Khởi động ở chế độ MOCK_HARDWARE=True.")
            self.write_lines("TRAM DINH DUONG", "SAN SANG CAN...")
        else:
            self._connect_hardware()

        self._initialized = True

    def _connect_hardware(self) -> bool:
        """Kết nối I2C tới PCF8574 trên Raspberry Pi 4."""
        if not HAS_RPLCD:
            self.last_error = "Thiếu thư viện RPLCD / smbus2."
            self.hardware_available = False
            logger.warning(f"[LCD] {self.last_error}")
            return False

        try:
            lcd = CharLCD(
                i2c_expander="PCF8574",
                address=self.address,
                port=self.port,
                cols=self.cols,
                rows=self.rows,
                dotsize=8,
                charmap="A00",
                auto_linebreaks=False,
            )
            lcd.clear()
            self._lcd = lcd
            self.hardware_available = True
            self.last_error = None
            logger.info(f"[LCD] Kết nối thành công LCD I2C 0x{self.address:02X}")
            self.write_lines("TRAM DINH DUONG", "KHOI DONG OK")
            return True
        except Exception as exc:
            self.last_error = f"Không tìm thấy LCD I2C 0x{self.address:02X}: {exc}"
            self.hardware_available = False
            self._lcd = None
            logger.warning(f"[LCD] {self.last_error} (Hệ thống vẫn tiếp tục chạy)")
            return False

    def write_lines(self, line1: str, line2: str) -> None:
        """Ghi 2 dòng nội dung lên LCD (có dirty-check chống nháy)."""
        l1 = format_lcd_line(line1, self.cols)
        l2 = format_lcd_line(line2, self.cols)

        with self._lock:
            if l1 == self._last_line1 and l2 == self._last_line2:
                return
            self._last_line1 = l1
            self._last_line2 = l2

        if self.mock_mode:
            self._mock_lcd.write(l1, l2)
            return

        if self._lcd is not None and self.hardware_available:
            try:
                self._lcd.cursor_pos = (0, 0)
                self._lcd.write_string(l1)
                self._lcd.cursor_pos = (1, 0)
                self._lcd.write_string(l2)
            except Exception as exc:
                self.last_error = f"Lỗi ghi I2C LCD: {exc}"
                logger.warning(f"[LCD] {self.last_error}")
                self.hardware_available = False
                self._lcd = None

    def display_station_status(
        self,
        state: str,
        weight_gram: float,
        food_name: str | None = None,
        kcal: float | None = None,
        quality_status: str | None = None,
    ) -> None:
        """Hiển thị thông tin cân nặng, tên thực phẩm và trạng thái kiểm định lên LCD 16x2."""
        st = state.upper().strip()
        w_int = int(round(abs(weight_gram)))

        if st == "IDLE":
            l1 = "SAN SANG CAN"
            l2 = f"{w_int}g - CHO HANG" if w_int > 0 else "DAT THUC PHAM..."
        elif st == "STABILIZING":
            l1 = "DANG ON DINH..."
            l2 = f"Trong luong:{w_int}g"
        elif st == "INSPECTING":
            l1 = "DANG NHAN DIEN"
            l2 = f"{w_int}g - AI CHECK"
        elif st == "CHECKOUT":
            name_clean = strip_vietnamese_diacritics(food_name or "THUC PHAM")[:10]
            if quality_status == "REJECTED":
                l1 = f"{name_clean} LOI!"
                l2 = f"{w_int}g TU CHOI"
            else:
                kcal_int = int(round(kcal or 0))
                l1 = f"{name_clean} {w_int}g"
                l2 = f"{kcal_int}kcal - DAT"
        else:
            l1 = st
            l2 = f"{w_int}g"

        self.write_lines(l1, l2)

    def get_status(self) -> dict[str, Any]:
        """Trả về trạng thái LCD và nội dung 2 dòng hiện tại cho Diagnostics."""
        with self._lock:
            l1 = self._last_line1
            l2 = self._last_line2
            err = self.last_error

        if self.mock_mode:
            status = "PASS (MOCK)"
            msg = "LCD 16x2 đang chạy giả lập (MOCK_HARDWARE=True)"
        elif self.hardware_available:
            status = "PASS"
            msg = f"LCD 16x2 I2C (PCF8574 @ 0x{self.address:02X}) hoạt động bình thường"
        else:
            status = "FAIL"
            msg = err or f"Chưa kết nối được LCD I2C 0x{self.address:02X}"

        return {
            "status": status,
            "mode": "mock" if self.mock_mode else "real",
            "available": True if self.mock_mode else self.hardware_available,
            "message": msg,
            "details": {
                "address": f"0x{self.address:02X}",
                "port": self.port,
                "cols": self.cols,
                "rows": self.rows,
                "line1": l1,
                "line2": l2,
                "last_error": err,
            },
        }
