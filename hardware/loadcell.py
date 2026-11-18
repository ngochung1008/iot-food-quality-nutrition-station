"""Driver cảm biến trọng lượng Loadcell + ADC 24-bit HX711 cho Raspberry Pi 4.

Kế thừa thuật toán ổn định từ IOT_CK:
- Đọc 24-bit nhị phân + xung thứ 25 chọn Gain 128 (Channel A), bù 2 có dấu.
- Lọc nhiễu bằng trung vị (statistics.median), loại mẫu bão hòa/lỗi (0x7FFFFF, -0x800000, -1).
- Trừ bì (Tare) 21 mẫu, dead-zone chống nhấp nháy quanh 0g.
- Hỗ trợ hiệu chuẩn trực tiếp từ Web/CLI và lưu vào hardware/calibration.json.
- Khi MOCK_HARDWARE=True: tự động dùng MockScaleDriver để chạy mượt trên Windows.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
import time
from collections import deque
from typing import Any

from backend.core.config import settings
from tests.mock_hardware import MockScaleDriver

logger = logging.getLogger("nutrition_station.hardware.loadcell")

try:
    import RPi.GPIO as GPIO  # type: ignore

    HAS_RPI_GPIO = True
except ImportError:
    GPIO = None  # type: ignore
    HAS_RPI_GPIO = False


class LoadcellManager:
    """Singleton quản lý cảm biến cân HX711 chạy luồng nền phi chặn."""

    _instance: LoadcellManager | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> LoadcellManager:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.mock_mode: bool = settings.mock_hardware
        self.dt_pin: int = settings.hx711_dt_pin
        self.sck_pin: int = settings.hx711_sck_pin
        self.invert_signal: bool = settings.hx711_invert_signal
        self.zero_band_g: float = settings.hx711_zero_band_g
        self.median_samples: int = settings.hx711_median_samples

        self._lock = threading.Lock()
        self.offset: float = 0.0
        self.scale_ratio: float = 420.0
        self.calibrated: bool = False

        self.last_grams: float = 0.0
        self.current_weight: float = 0.0
        self.is_stable: bool = False
        self.scale_online: bool = False
        self.hardware_available: bool = False
        self.last_sample_time: float = 0.0
        self.last_error: str | None = None

        self._history: deque[float] = deque(maxlen=20)
        self._stable_since: float | None = None
        self._mock_driver = MockScaleDriver()

        # 1. Nạp hệ số hiệu chuẩn từ hardware/calibration.json
        self.load_calibration()
        self._mock_driver.scale_ratio = self.scale_ratio

        # 2. Khởi tạo GPIO nếu chạy thật trên Raspberry Pi 4
        if self.mock_mode:
            self.hardware_available = False
            self.scale_online = True
            self.last_sample_time = time.time()
            logger.info("[LOADCELL] Khởi động ở chế độ MOCK_HARDWARE=True (Windows/Dev).")
        else:
            self._init_gpio()

        # 3. Chạy thread đọc cân liên tục (~10Hz)
        self._stop_event = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="hx711-reader",
            daemon=True,
        )
        self._reader_thread.start()
        self._initialized = True

    def _init_gpio(self) -> None:
        """Thiết lập chân GPIO BCM cho HX711 trên Raspberry Pi 4."""
        if not HAS_RPI_GPIO:
            self.last_error = "MOCK_HARDWARE=False nhưng thiếu thư viện RPi.GPIO trên hệ thống."
            self.hardware_available = False
            logger.error(f"[LOADCELL] {self.last_error}")
            return

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.sck_pin, GPIO.OUT)
            GPIO.setup(self.dt_pin, GPIO.IN)
            GPIO.output(self.sck_pin, False)
            self.hardware_available = True
            logger.info(
                f"[LOADCELL] Đã thiết lập GPIO HX711 (DT=GPIO{self.dt_pin}, SCK=GPIO{self.sck_pin}, Invert={self.invert_signal})"
            )
            time.sleep(0.15)
            self.tare(samples=21)
        except Exception as exc:
            self.last_error = f"Lỗi khởi tạo GPIO HX711: {exc}"
            self.hardware_available = False
            logger.error(f"[LOADCELL] {self.last_error}")

    def load_calibration(self) -> None:
        """Đọc scale_ratio từ hardware/calibration.json."""
        cal_file = settings.calibration_file
        if not cal_file.exists():
            self.calibrated = False
            self.scale_ratio = 420.0
            self.last_error = f"Chưa tìm thấy {cal_file.name}, cần hiệu chuẩn cân."
            logger.warning(f"[LOADCELL] {self.last_error}")
            return

        try:
            with open(cal_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            ratio = float(data.get("scale_ratio", 0))
            if ratio != 0:
                self.scale_ratio = ratio
                self.calibrated = True
                logger.info(f"[LOADCELL] Đã nạp scale_ratio={ratio:.4f} từ {cal_file.name}")
            else:
                self.calibrated = False
                self.last_error = "scale_ratio trong calibration.json bằng 0."
        except Exception as exc:
            self.calibrated = False
            self.last_error = f"Lỗi đọc calibration.json: {exc}"
            logger.warning(f"[LOADCELL] {self.last_error}")

    def save_calibration(self, ratio: float, known_weight_g: float | None = None) -> bool:
        """Lưu hệ số hiệu chuẩn vào hardware/calibration.json."""
        if ratio == 0:
            return False
        with self._lock:
            self.scale_ratio = float(ratio)
            self.calibrated = True
            self._mock_driver.scale_ratio = self.scale_ratio

        payload: dict[str, Any] = {
            "scale_ratio": round(float(ratio), 4),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if known_weight_g is not None:
            payload["reference_weight_g"] = float(known_weight_g)

        try:
            settings.calibration_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings.calibration_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"[LOADCELL] Đã lưu scale_ratio={self.scale_ratio:.4f} vào calibration.json")
            return True
        except Exception as exc:
            logger.error(f"[LOADCELL] Không thể lưu calibration.json: {exc}")
            return False

    def is_ready(self) -> bool:
        """HX711 kéo chân DT xuống LOW khi có mẫu mới sẵn sàng."""
        if not HAS_RPI_GPIO:
            return False
        return GPIO.input(self.dt_pin) == 0

    def read_raw(self) -> int:
        """Đọc 24-bit nhị phân từ HX711 kèm xung thứ 25 chốt Gain 128."""
        if self.mock_mode:
            return int(round(self._mock_driver.read_raw_simulated()))

        if not HAS_RPI_GPIO or not self.hardware_available:
            raise RuntimeError("GPIO HX711 không khả dụng.")

        timeout = 0.0
        while not self.is_ready():
            time.sleep(0.001)
            timeout += 0.001
            if timeout > 0.3:
                raise TimeoutError("HX711 không phản hồi (Timeout DOUT > 0.3s).")

        count = 0
        for _ in range(24):
            GPIO.output(self.sck_pin, True)
            time.sleep(0.000001)
            count = count << 1
            GPIO.output(self.sck_pin, False)
            time.sleep(0.000001)
            if GPIO.input(self.dt_pin):
                count += 1

        # Xung thứ 25: Gain 128 Channel A (độ trễ 1µs tương thích rpi-lgpio)
        GPIO.output(self.sck_pin, True)
        time.sleep(0.000001)
        GPIO.output(self.sck_pin, False)
        time.sleep(0.000001)

        # Bù 2 cho số nguyên có dấu 24-bit
        if count & 0x800000:
            count -= 0x1000000

        return -count if self.invert_signal else count

    def read_median_raw(self, samples: int = 9) -> float:
        """Lọc gai nhiễu bằng trung vị (Median) qua N mẫu."""
        if self.mock_mode:
            vals = [self._mock_driver.read_raw_simulated() for _ in range(max(3, min(samples, 11)))]
            return float(statistics.median(vals))

        values: list[int] = []
        for _ in range(samples):
            try:
                v = self.read_raw()
                if v not in (0x7FFFFF, -0x800000, -1):
                    values.append(v)
            except TimeoutError:
                pass
            time.sleep(0.01)

        if not values:
            raise RuntimeError("Mất kết nối HX711 (không đọc được mẫu hợp lệ).")
        return float(statistics.median(values))

    def tare(self, samples: int = 21) -> bool:
        """Trừ bì (Zero balance): đặt khối lượng nền hiện tại làm điểm 0."""
        if self.mock_mode:
            self.offset = self._mock_driver.tare()
            with self._lock:
                self.last_grams = 0.0
                self.current_weight = 0.0
                self.is_stable = False
                self._history.clear()
                self._stable_since = None
            logger.info("[LOADCELL MOCK] Đã Tare cân về 0.0g")
            return True

        if not HAS_RPI_GPIO or not self.hardware_available:
            self.last_error = "Không thể Tare: HX711 chưa kết nối."
            return False

        try:
            self.offset = self.read_median_raw(samples)
            with self._lock:
                self.last_grams = 0.0
                self.current_weight = 0.0
                self.is_stable = False
                self._history.clear()
                self._stable_since = None
            logger.info(f"[LOADCELL] Đã Tare thành công (offset={self.offset:.1f})")
            return True
        except Exception as exc:
            self.last_error = f"Tare thất bại: {exc}"
            logger.error(f"[LOADCELL] {self.last_error}")
            return False

    def calibrate_with_known_weight(self, known_weight_g: float, invert_if_negative: bool = True) -> dict[str, Any]:
        """Thực hiện bước 2 hiệu chuẩn cân: đo vật chuẩn và tính toán scale_ratio mới."""
        if known_weight_g <= 0:
            return {"ok": False, "error": "Khối lượng chuẩn phải lớn hơn 0g."}

        try:
            raw_loaded = self.read_median_raw(samples=25)
            if self.mock_mode:
                # Ở chế độ mock, giả lập delta hợp lý theo vật mẫu để test quy trình calibration UI
                delta = known_weight_g * self.scale_ratio
            else:
                delta = raw_loaded - self.offset

            if abs(delta) < 500:
                return {
                    "ok": False,
                    "error": f"Độ lệch ADC quá nhỏ (|delta|={abs(delta):.0f} < 500). Kiểm tra vật mẫu đã đặt lên cân chưa.",
                }

            ratio = delta / float(known_weight_g)
            if ratio < 0 and invert_if_negative:
                ratio = -ratio

            saved = self.save_calibration(ratio, known_weight_g=known_weight_g)
            return {
                "ok": saved,
                "scale_ratio": round(ratio, 4),
                "raw_loaded": round(raw_loaded, 1),
                "offset": round(self.offset, 1),
                "delta": round(delta, 1),
                "message": f"Hiệu chuẩn thành công! scale_ratio = {ratio:.4f}",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Lỗi khi hiệu chuẩn: {exc}"}

    def invert_calibration_sign(self) -> float:
        """Đảo dấu scale_ratio trong calibration.json khi lực bị ngược chiều."""
        new_ratio = -self.scale_ratio
        self.save_calibration(new_ratio)
        return new_ratio

    def get_grams(self, samples: int = 9) -> float:
        """Đọc khối lượng hiện tại (gram) kèm dead-zone chống nhiễu quanh 0."""
        if self.mock_mode:
            grams = self._mock_driver.read_grams()
            return 0.0 if grams < self.zero_band_g else float(grams)

        raw = self.read_median_raw(samples)
        if self.scale_ratio == 0:
            grams = 0.0
        else:
            grams = abs((raw - self.offset) / self.scale_ratio)
        return 0.0 if grams < self.zero_band_g else float(grams)

    def _reader_loop(self) -> None:
        """Luồng đọc nền liên tục mỗi ~100ms (10Hz)."""
        interval = 1.0 / max(1, settings.weight_sample_hz)
        while not self._stop_event.is_set():
            started = time.time()
            try:
                if self.mock_mode or (self.hardware_available and HAS_RPI_GPIO):
                    # Dùng 3 mẫu trung vị ở luồng nền để tăng tốc độ phản hồi ~3 lần
                    grams = self.get_grams(samples=3)
                    now = time.time()
                    with self._lock:
                        self.last_grams = round(abs(grams), 1)
                        self.last_sample_time = now
                        self.scale_online = True
                        self.last_error = None
                        self._update_stability(self.last_grams, now)
                else:
                    with self._lock:
                        self.scale_online = False
                        self.is_stable = False
                    time.sleep(0.25)
            except Exception as exc:
                now = time.time()
                with self._lock:
                    self.last_error = f"Lỗi đọc HX711: {exc}"
                    if now - self.last_sample_time > 2.0:
                        self.scale_online = False
                        self.is_stable = False
                time.sleep(0.05)

            elapsed = time.time() - started
            time.sleep(max(0.02, interval - elapsed))

    def _update_stability(self, weight: float, now: float) -> None:
        """Kiểm tra cân ổn định khi Δm < STABILITY_DELTA_G trong STABILITY_HOLD_S giây."""
        self._history.append(weight)
        prev = self._history[-2] if len(self._history) >= 2 else weight
        delta = abs(weight - prev)

        if (
            weight >= settings.detect_weight_g
            or (self._stable_since is not None and weight >= settings.idle_weight_g)
        ) and delta < settings.stability_delta_g:
            if self._stable_since is None:
                self._stable_since = now
            self.is_stable = (now - self._stable_since) >= settings.stability_hold_s
        else:
            self._stable_since = None
            self.is_stable = False

        self.current_weight = weight

    def read_filtered_weight(self) -> float:
        """Đọc giá trị gram đã cache từ luồng nền (không block State Machine)."""
        with self._lock:
            now = time.time()
            if not self.mock_mode and (now - self.last_sample_time > 2.0):
                self.scale_online = False
                self.is_stable = False
                return 0.0
            return abs(float(self.current_weight))

    def set_simulated_weight(self, grams: float) -> None:
        """Thiết lập khối lượng giả lập khi MOCK_HARDWARE=True."""
        if not self.mock_mode:
            logger.warning("[LOADCELL] Từ chối giả lập vì đang chạy phần cứng thật.")
            return
        val = round(max(0.0, float(grams)), 1)
        self._mock_driver.set_weight(val)
        with self._lock:
            self.last_grams = val
            self.current_weight = val
            self.last_sample_time = time.time()
            self.scale_online = True

    def cleanup(self) -> None:
        """Dừng luồng đọc và giải phóng tài nguyên GPIO an toàn."""
        self._stop_event.set()
        if HAS_RPI_GPIO and GPIO is not None and not self.mock_mode:
            try:
                GPIO.cleanup()
                logger.info("[LOADCELL] Đã giải phóng GPIO HX711.")
            except Exception as exc:
                logger.warning(f"[LOADCELL] Lỗi GPIO.cleanup(): {exc}")

    def get_status(self) -> dict[str, Any]:
        """Trả về trạng thái chi tiết phục vụ trang Hardware Diagnostics."""
        with self._lock:
            grams = self.last_grams
            online = self.scale_online
            stable = self.is_stable
            calibrated = self.calibrated
            ratio = self.scale_ratio
            offset = self.offset
            err = self.last_error
            last_time = self.last_sample_time

        is_alive = online and (time.time() - last_time <= 2.0 if last_time > 0 else False)
        if self.mock_mode:
            status = "PASS (MOCK)"
            msg = "Cảm biến HX711 đang chạy giả lập (MOCK_HARDWARE=True)"
        elif is_alive and calibrated:
            status = "PASS"
            msg = f"HX711 Online, đã hiệu chuẩn (scale_ratio={ratio:.4f})"
        elif is_alive:
            status = "WARN"
            msg = "HX711 Online nhưng chưa hiệu chuẩn (thiếu calibration.json)"
        else:
            status = "FAIL"
            msg = err or "Cân HX711 mất tín hiệu (> 2s không có mẫu mới)"

        return {
            "status": status,
            "mode": "mock" if self.mock_mode else "real",
            "scale_online": True if self.mock_mode else is_alive,
            "scale_calibrated": calibrated,
            "last_grams": grams,
            "is_stable": stable,
            "message": msg,
            "details": {
                "dt_pin": self.dt_pin,
                "sck_pin": self.sck_pin,
                "invert_signal": self.invert_signal,
                "zero_band_g": self.zero_band_g,
                "scale_ratio": round(ratio, 4),
                "tare_offset": round(offset, 1),
                "last_error": err,
            },
        }
