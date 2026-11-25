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
        self._io_lock = threading.RLock()
        self._raw_cond = threading.Condition(self._lock)
        self.offset: float = 0.0
        self.scale_ratio: float = -392.25
        self.calibrated: bool = False

        self.last_grams: float = 0.0
        self.current_weight: float = 0.0
        self.is_stable: bool = False
        self.scale_online: bool = False
        self.is_online: bool = False
        self.hardware_available: bool = False
        self.last_sample_time: float = 0.0
        self.last_raw_timestamp: float = 0.0
        self.last_error: str | None = None
        self.station_state: str = "IDLE"

        self._raw_buffer: deque[tuple[float, float]] = deque(maxlen=30)
        self._raw_seq: int = 0
        self._history: deque[float] = deque(maxlen=20)
        self._rolling_grams: deque[float] = deque(maxlen=3)
        self._spike_skip_count: int = 0
        self._bitshift_skip_count: int = 0
        self._step_jump_count: int = 0
        self._consecutive_timeouts: int = 0
        self._stable_since: float | None = None
        self._drift_since: float | None = None
        self._drift_raw_samples: deque[float] = deque(maxlen=40)
        self.auto_zero_min_g: float = 0.1
        self.auto_zero_max_g: float = 0.8
        self.auto_zero_hold_s: float = 4.0
        self._mock_driver = MockScaleDriver()

        # 1. Nạp hệ số hiệu chuẩn từ hardware/calibration.json
        self.load_calibration()
        self._mock_driver.scale_ratio = self.scale_ratio

        # 2. Khởi tạo GPIO nếu chạy thật trên Raspberry Pi 4
        if self.mock_mode:
            self.hardware_available = False
            self.scale_online = True
            self.is_online = True
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
            # Chờ 0.5s để cảm biến & nắp nhôm mở rộng ổn định trước khi Tare 21 mẫu làm mốc 0.0g
            time.sleep(0.5)
            self.tare(samples=21)
        except Exception as exc:
            self.last_error = f"Lỗi khởi tạo GPIO HX711: {exc}"
            self.hardware_available = False
            logger.error(f"[LOADCELL] {self.last_error}")

    def load_calibration(self) -> None:
        """Đọc scale_ratio và tare_offset từ hardware/calibration.json.

        Nếu chưa có file calibration.json trên máy mới, tự động khởi tạo từ
        hardware/calibration.example.json (scale_ratio = -392.25).
        Tuyệt đối không tự ý ghi đè calibration.json nếu file đã tồn tại.
        """
        cal_file = settings.calibration_file
        example_file = cal_file.with_name("calibration.example.json")
        if not cal_file.exists():
            if example_file.exists():
                try:
                    cal_file.parent.mkdir(parents=True, exist_ok=True)
                    cal_file.write_text(example_file.read_text(encoding="utf-8"), encoding="utf-8")
                    logger.info(
                        f"[LOADCELL] Đã khởi tạo {cal_file.name} từ {example_file.name}."
                    )
                except Exception as exc:
                    logger.warning(f"[LOADCELL] Không thể sao chép {example_file.name}: {exc}")

            if not cal_file.exists():
                self.calibrated = False
                self.scale_ratio = -392.25
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
                if "tare_offset" in data and data["tare_offset"] is not None:
                    self.offset = float(data["tare_offset"])
                logger.info(
                    f"[LOADCELL] Đã nạp scale_ratio={ratio:.4f}, tare_offset={self.offset:.1f} từ {cal_file.name}"
                )
            else:
                self.calibrated = False
                self.last_error = "scale_ratio trong calibration.json bằng 0."
        except Exception as exc:
            self.calibrated = False
            self.last_error = f"Lỗi đọc calibration.json: {exc}"
            logger.warning(f"[LOADCELL] {self.last_error}")

    def _persist_calibration_file(self, known_weight_g: float | None = None) -> bool:
        """Ghi scale_ratio hiện tại và tare_offset ổn định vào hardware/calibration.json."""
        existing: dict[str, Any] = {}
        cal_file = settings.calibration_file
        if cal_file.exists():
            try:
                with open(cal_file, "r", encoding="utf-8-sig") as f:
                    existing = json.load(f) or {}
            except Exception:
                existing = {}

        # Giữ nguyên scale_ratio thực tế trong file nếu đã có và self.calibrated chưa thay đổi
        ratio_to_save = self.scale_ratio
        if ratio_to_save == 0 and float(existing.get("scale_ratio", 0)) != 0:
            ratio_to_save = float(existing["scale_ratio"])

        payload: dict[str, Any] = {
            **existing,
            "scale_ratio": round(float(ratio_to_save), 4),
            "tare_offset": round(float(self.offset), 1),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if known_weight_g is not None:
            payload["reference_weight_g"] = float(known_weight_g)

        try:
            cal_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cal_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            logger.error(f"[LOADCELL] Không thể lưu calibration.json: {exc}")
            return False

    def save_calibration(self, ratio: float, known_weight_g: float | None = None) -> bool:
        """Lưu hệ số hiệu chuẩn vào hardware/calibration.json."""
        if ratio == 0:
            return False
        with self._lock:
            self.scale_ratio = float(ratio)
            self.calibrated = True
            self._mock_driver.scale_ratio = self.scale_ratio

        ok = self._persist_calibration_file(known_weight_g=known_weight_g)
        if ok:
            logger.info(
                f"[LOADCELL] Đã lưu scale_ratio={self.scale_ratio:.4f}, tare_offset={self.offset:.1f} vào calibration.json"
            )
        return ok

    def is_ready(self) -> bool:
        """HX711 kéo chân DT xuống LOW khi có mẫu mới sẵn sàng."""
        if not HAS_RPI_GPIO:
            return False
        return GPIO.input(self.dt_pin) == 0

    def _reset_hx711(self) -> None:
        """Reset phần cứng chip HX711 bằng xung SCK HIGH 100µs rồi hạ LOW để tự phục hồi."""
        if not HAS_RPI_GPIO or GPIO is None or not self.hardware_available:
            return
        try:
            GPIO.output(self.sck_pin, True)
            time.sleep(0.0001)
            GPIO.output(self.sck_pin, False)
            time.sleep(0.005)
            logger.warning("[LOADCELL] Đã reset HX711 (SCK HIGH 100µs -> LOW) sau 3 lần Timeout DOUT.")
        except Exception as exc:
            logger.debug(f"[LOADCELL] Lỗi _reset_hx711(): {exc}")

    def read_raw(self) -> int | None:
        """Đọc 24-bit nhị phân từ HX711 kèm xung thứ 25; trả None nếu bị ngắt > 12ms hoặc mẫu lỗi."""
        if self.mock_mode:
            return int(round(self._mock_driver.read_raw_simulated()))

        if not HAS_RPI_GPIO or not self.hardware_available:
            raise RuntimeError("GPIO HX711 không khả dụng.")

        timeout = 0.0
        while not self.is_ready():
            time.sleep(0.001)
            timeout += 0.001
            if timeout > 0.3:
                self._consecutive_timeouts = getattr(self, "_consecutive_timeouts", 0) + 1
                if self._consecutive_timeouts >= 3:
                    self.last_error = "HX711 không phản hồi (Timeout DOUT > 0.3s)."
                    self._consecutive_timeouts = 0
                    self._reset_hx711()
                raise TimeoutError("HX711 không phản hồi (Timeout DOUT > 0.3s).")
        self._consecutive_timeouts = 0

        t_start = time.perf_counter()
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
        t_elapsed = time.perf_counter() - t_start

        # Nếu vòng lặp 24-bit mất > 12ms -> OS context switch làm sai xung SCK (>60µs) -> bỏ qua
        if t_elapsed > 0.012:
            logger.debug(f"[LOADCELL] Bỏ qua mẫu HX711 bị ngắt quãng CPU (t_elapsed={t_elapsed * 1000:.2f}ms)")
            return None

        if count in (0, 0xFFFFFF, 0x7FFFFF, 0x800000):
            return None

        # Bù 2 cho số nguyên có dấu 24-bit
        if count & 0x800000:
            count -= 0x1000000

        val = -count if self.invert_signal else count
        if val in (0, -1, 0x7FFFFF, -0x800000):
            return None
        return val

    @staticmethod
    def filter_median_outliers(values: list[float] | list[int], tolerance_ratio: float = 0.25) -> float:
        """Lọc nhiễu: tìm trung vị, loại bỏ ngoại lai lệch quá ±25% so với trung vị rồi tính trung bình."""
        if not values:
            raise ValueError("Danh sách mẫu trống.")
        med = float(statistics.median(values))
        threshold = max(abs(med) * tolerance_ratio, 150.0)
        inliers = [float(v) for v in values if abs(float(v) - med) <= threshold]
        if inliers:
            return float(statistics.mean(inliers))
        return med

    @staticmethod
    def filter_trimmed_median(values: list[float] | list[int]) -> float:
        """Loại bỏ 25% giá trị cao nhất và 25% thấp nhất rồi lấy trung vị để Tare/Hiệu chuẩn chuẩn xác."""
        if not values:
            raise ValueError("Danh sách mẫu trống.")
        sorted_vals = sorted(float(v) for v in values)
        if len(sorted_vals) >= 4:
            trim = max(1, len(sorted_vals) // 4)
            core = sorted_vals[trim:-trim]
            if core:
                return float(statistics.median(core))
        return float(statistics.median(sorted_vals))

    def _read_single_raw_hardware(self) -> int | None:
        """Đọc đúng 1 mẫu 24-bit từ HX711 (chỉ dùng nội bộ trong luồng đọc hoặc lúc khởi tạo)."""
        with self._io_lock:
            return self.read_raw()

    def _collect_clean_raw_samples(self, samples: int) -> list[int]:
        """Thu thập N mẫu sạch lúc khởi động trước khi bật luồng nền."""
        values: list[int] = []
        attempts = 0
        max_attempts = max(samples * 3, samples + 12)
        while len(values) < samples and attempts < max_attempts:
            attempts += 1
            try:
                v = self._read_single_raw_hardware()
                if v is not None and v not in (0x7FFFFF, -0x800000, -1, 0):
                    values.append(v)
                    with self._lock:
                        now = time.time()
                        self._raw_buffer.append((now, float(v)))
                        self._raw_seq += 1
                        self.last_raw_timestamp = now
                        self.last_sample_time = now
                        self.scale_online = True
            except TimeoutError:
                pass
            time.sleep(0.002)

        if not values:
            raise RuntimeError("Mất kết nối HX711 (không đọc được mẫu hợp lệ).")
        return values

    def _collect_from_reader_buffer(self, samples: int = 15, timeout_s: float = 3.0) -> list[float]:
        """Lấy N mẫu thô mới nhất từ bộ đệm vòng của _reader_loop (không đụng GPIO trực tiếp)."""
        reader = getattr(self, "_reader_thread", None)
        if reader is None or not reader.is_alive():
            if self.mock_mode:
                return [float(self._mock_driver.read_raw_simulated()) for _ in range(max(4, samples))]
            return [float(v) for v in self._collect_clean_raw_samples(samples)]

        deadline = time.monotonic() + timeout_s
        collected: list[float] = []
        with self._raw_cond:
            last_seen_seq = self._raw_seq
            while len(collected) < samples:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if self._raw_seq <= last_seen_seq:
                    self._raw_cond.wait(timeout=min(remaining, 0.25))
                    continue

                # Trích xuất các mẫu mới vừa được _reader_loop đẩy vào bộ đệm vòng
                new_count = min(len(self._raw_buffer), self._raw_seq - last_seen_seq)
                recent_slice = list(self._raw_buffer)[-new_count:]
                for _, raw_val in recent_slice:
                    collected.append(float(raw_val))
                    if len(collected) >= samples:
                        break
                last_seen_seq = self._raw_seq

        if len(collected) >= min(5, samples):
            return collected

        # Fallback an toàn nếu cân đang giữ ổn định và vừa có mẫu mới < 1.5s
        with self._lock:
            now = time.time()
            if (now - self.last_raw_timestamp) <= 1.5 and len(self._raw_buffer) >= min(5, samples):
                return [val for _, val in list(self._raw_buffer)[-samples:]]

        raise RuntimeError("Timeout 3.0s chờ mẫu từ luồng đọc HX711 (kiểm tra dây DT/SCK).")

    def read_median_raw(self, samples: int = 7) -> float:
        """Lấy trung vị loại ngoại lai ±25% (trong HTTP thread chỉ đọc từ bộ đệm vòng)."""
        if self.mock_mode:
            vals = [self._mock_driver.read_raw_simulated() for _ in range(max(3, min(samples, 11)))]
            return self.filter_median_outliers(vals)

        reader = getattr(self, "_reader_thread", None)
        if reader is not None and reader.is_alive():
            with self._lock:
                recent = [val for _, val in list(self._raw_buffer)[-samples:]]
            if recent:
                return self.filter_median_outliers(recent)

        values = self._collect_clean_raw_samples(samples)
        return self.filter_median_outliers(values)

    def read_trimmed_median_raw(self, samples: int = 15, timeout_s: float = 3.0) -> float:
        """Lấy N mẫu mới nhất từ bộ đệm _reader_loop, bỏ 25% đầu/cuối trước khi tính trung vị."""
        if self.mock_mode:
            vals = [self._mock_driver.read_raw_simulated() for _ in range(max(4, min(samples, 25)))]
            return self.filter_trimmed_median(vals)
        values = self._collect_from_reader_buffer(samples=samples, timeout_s=timeout_s)
        return self.filter_trimmed_median(values)

    def tare(self, samples: int = 21) -> bool:
        """Trừ bì (Zero balance): lấy Trimmed Median (bỏ 25% đầu/cuối) từ bộ đệm luồng nền.

        Mặc định trừ bì cả khay/nắp nhôm đi kèm.
        Tuyệt đối không gọi read_raw() trực tiếp khi _reader_loop đang chạy để tránh xung đột GPIO.
        """
        if self.mock_mode:
            with self._io_lock:
                self.offset = self._mock_driver.tare()
            with self._lock:
                self.last_grams = 0.0
                self.current_weight = 0.0
                self.is_stable = False
                self._history.clear()
                self._rolling_grams.clear()
                self._spike_skip_count = 0
                self._bitshift_skip_count = 0
                self._step_jump_count = 0
                self._stable_since = None
                self._drift_since = None
                self._drift_raw_samples.clear()
            logger.info("[LOADCELL MOCK] Đã Tare cân (cả nắp/khay) về 0.0g")
            return True

        if not HAS_RPI_GPIO or not self.hardware_available:
            self.last_error = "Không thể Tare: HX711 chưa kết nối."
            return False

        try:
            # Nếu luồng đọc nền đã chạy, lấy 15 mẫu thô mới nhất từ bộ đệm vòng (tối đa 3.0s)
            reader = getattr(self, "_reader_thread", None)
            target_samples = min(samples, 15) if (reader is not None and reader.is_alive()) else samples
            new_offset = self.read_trimmed_median_raw(target_samples, timeout_s=3.0)
            with self._lock:
                self.offset = new_offset
                self.last_grams = 0.0
                self.current_weight = 0.0
                self.is_stable = False
                self._history.clear()
                self._rolling_grams.clear()
                self._spike_skip_count = 0
                self._bitshift_skip_count = 0
                self._step_jump_count = 0
                self._stable_since = None
                self._drift_since = None
                self._drift_raw_samples.clear()
            logger.info(f"[LOADCELL] Đã Tare {target_samples} mẫu thành công (tare_offset={self.offset:.1f})")
            return True
        except Exception as exc:
            self.last_error = f"Tare thất bại: {exc}"
            logger.error(f"[LOADCELL] {self.last_error}")
            return False

    def calibrate_with_known_weight(self, known_weight_g: float, invert_if_negative: bool = True) -> dict[str, Any]:
        """Thực hiện bước 2 hiệu chuẩn cân: lấy 8 mẫu từ bộ đệm _reader_loop và kiểm tra khóa an toàn."""
        if known_weight_g <= 0:
            return {"ok": False, "error": "Khối lượng chuẩn phải lớn hơn 0g."}

        try:
            raw_loaded = self.read_trimmed_median_raw(samples=8, timeout_s=3.0)
            if self.mock_mode:
                # Ở chế độ mock, giả lập delta hợp lý theo vật mẫu để test quy trình calibration UI
                diff = known_weight_g * self.scale_ratio
            else:
                diff = raw_loaded - self.offset

            if abs(diff) < 3000:
                return {
                    "ok": False,
                    "error": "Tín hiệu cảm biến chưa ổn định hoặc chưa đặt đủ vật mẫu lên cân (diff quá nhỏ). Vui lòng thử lại.",
                }

            ratio = diff / float(known_weight_g)
            if ratio < 0 and invert_if_negative:
                ratio = -ratio

            if abs(ratio) < 150 or abs(ratio) > 2500:
                return {
                    "ok": False,
                    "error": "Tín hiệu cảm biến chưa ổn định hoặc chưa đặt đủ vật mẫu lên cân (diff quá nhỏ). Vui lòng thử lại.",
                }

            saved = self.save_calibration(ratio, known_weight_g=known_weight_g)
            return {
                "ok": saved,
                "scale_ratio": round(ratio, 4),
                "raw_loaded": round(raw_loaded, 1),
                "offset": round(self.offset, 1),
                "delta": round(diff, 1),
                "message": f"Hiệu chuẩn thành công! scale_ratio = {ratio:.4f}",
            }
        except Exception as exc:
            return {"ok": False, "error": f"Lỗi khi hiệu chuẩn: {exc}"}

    def invert_calibration_sign(self) -> float:
        """Đảo dấu scale_ratio trong calibration.json khi lực bị ngược chiều."""
        new_ratio = -self.scale_ratio
        self.save_calibration(new_ratio)
        return new_ratio

    def _read_raw_and_unclamped_grams(self, samples: int = 3) -> tuple[float, float]:
        """Đọc giá trị ADC trung vị và gram chưa cắt dead-zone để phục vụ Auto-Zero Drift."""
        raw = self.read_median_raw(samples)
        if self.mock_mode:
            ratio = self._mock_driver.scale_ratio if self._mock_driver.scale_ratio != 0 else 420.0
            grams = max(0.0, (raw - self._mock_driver.offset) / ratio)
            return raw, float(grams)

        if self.scale_ratio == 0:
            return raw, 0.0
        grams = abs((raw - self.offset) / self.scale_ratio)
        return raw, float(grams)

    def get_grams(self, samples: int = 9) -> float:
        """Đọc khối lượng hiện tại (gram) kèm dead-zone chống nhiễu quanh 0."""
        _, grams = self._read_raw_and_unclamped_grams(samples=samples)
        return 0.0 if grams < self.zero_band_g else float(grams)

    def _track_auto_zero_drift(self, raw_adc: float, unclamped_g: float, now: float) -> bool:
        """Tự động bù trôi điểm 0 khi IDLE và cân trôi nhẹ 0.1g..0.8g liên tục >= 4.0s."""
        drift_g = abs(float(unclamped_g))
        if (
            self.station_state == "IDLE"
            and self.auto_zero_min_g <= drift_g <= self.auto_zero_max_g
        ):
            self._drift_raw_samples.append(float(raw_adc))
            if self._drift_since is None:
                self._drift_since = now
                return False

            if (now - self._drift_since) >= self.auto_zero_hold_s and self._drift_raw_samples:
                new_offset = self.filter_median_outliers(list(self._drift_raw_samples))
                if self.mock_mode:
                    self._mock_driver.tare()
                    self.offset = self._mock_driver.offset
                else:
                    self.offset = float(new_offset)

                self._rolling_grams.clear()
                self._history.clear()
                self._spike_skip_count = 0
                self._step_jump_count = 0
                self.last_grams = 0.0
                self.current_weight = 0.0
                self._drift_since = None
                self._drift_raw_samples.clear()
                logger.info(
                    f"[LOADCELL] Auto-Zero Drift: đã bù trôi nhẹ {drift_g:.2f}g -> 0.0g (tare_offset={self.offset:.1f})"
                )
                return True
            return False

        self._drift_since = None
        self._drift_raw_samples.clear()
        return False

    def _read_raw_once_for_loop(self) -> float:
        """Đọc 1 mẫu thô sạch duy nhất từ GPIO (hoặc Mock) cho _reader_loop."""
        if self.mock_mode:
            return float(self._mock_driver.read_raw_simulated())

        for _ in range(3):
            v = self._read_single_raw_hardware()
            if v is not None:
                return float(v)
            time.sleep(0.005)
        raise RuntimeError("Không đọc được mẫu HX711 hợp lệ.")

    def _raw_to_unclamped_grams(self, raw_adc: float) -> float:
        if self.mock_mode:
            ratio = self._mock_driver.scale_ratio if self._mock_driver.scale_ratio != 0 else -392.25
            return max(0.0, (raw_adc - self._mock_driver.offset) / ratio)
        if self.scale_ratio == 0:
            return 0.0
        return abs((raw_adc - self.offset) / self.scale_ratio)

    def _reader_loop(self) -> None:
        """Luồng ĐỘC QUYỀN đọc GPIO HX711 ~15-20Hz: đẩy 30 mẫu thô sạch vào bộ đệm vòng & lọc 3 mẫu."""
        interval = 0.05
        while not self._stop_event.is_set():
            started = time.time()
            try:
                if self.mock_mode or (self.hardware_available and HAS_RPI_GPIO):
                    raw_adc = self._read_raw_once_for_loop()
                    now = time.time()
                    with self._raw_cond:
                        self._raw_buffer.append((now, raw_adc))
                        self._raw_seq += 1
                        self.last_raw_timestamp = now
                        self.last_sample_time = now
                        self._raw_cond.notify_all()

                        unclamped_g = self._raw_to_unclamped_grams(raw_adc)
                        sample_g = 0.0 if unclamped_g < self.zero_band_g else float(unclamped_g)
                        smooth_g = self._apply_rolling_median_filter(sample_g)
                        self.last_grams = round(abs(smooth_g), 1)
                        self._track_auto_zero_drift(raw_adc, unclamped_g, now)
                        self._update_stability(self.last_grams, now)
                        self._consecutive_timeouts = 0
                        self.last_error = None
                        self.scale_online = True
                        self.is_online = True
                else:
                    with self._lock:
                        self.scale_online = False
                        self.is_online = False
                        self.is_stable = False
                    time.sleep(0.25)
            except TimeoutError:
                now = time.time()
                with self._lock:
                    if now - self.last_sample_time > 2.0:
                        self.scale_online = False
                        self.is_online = False
                        self.is_stable = False
                time.sleep(0.05)
            except Exception as exc:
                now = time.time()
                with self._lock:
                    if getattr(self, "_consecutive_timeouts", 0) >= 3 or "Timeout DOUT" not in str(exc):
                        self.last_error = f"Lỗi đọc HX711: {exc}"
                    if now - self.last_sample_time > 2.0:
                        self.scale_online = False
                        self.is_online = False
                        self.is_stable = False
                time.sleep(0.05)

            elapsed = time.time() - started
            time.sleep(max(0.01, interval - elapsed))

    def _apply_rolling_median_filter(self, sample_g: float) -> float:
        """Rolling Median 3 mẫu: loại ngay dịch bit x2 / 0.5x & cập nhật tức thì khi đổi > 5.0g trong 2 nhịp."""
        val = max(0.0, float(sample_g))
        if len(self._rolling_grams) >= 2:
            med = float(statistics.median(self._rolling_grams))
            is_bitshift_2x = med >= 10.0 and (1.85 * med <= val <= 2.15 * med)
            is_bitshift_half = med >= 10.0 and (0.45 * med <= val <= 0.55 * med)
            if is_bitshift_2x or is_bitshift_half:
                if self._bitshift_skip_count < 8:
                    self._bitshift_skip_count += 1
                    self._step_jump_count = 0
                    logger.debug(f"[LOADCELL] Loại mẫu dịch bit ({val:.1f}g vs median {med:.1f}g)")
                    return 0.0 if med < self.zero_band_g else med

            is_zero_dropout = med >= 15.0 and val < 2.0
            if is_zero_dropout and self._spike_skip_count < 2:
                self._spike_skip_count += 1
                self._step_jump_count = 0
                return 0.0 if med < self.zero_band_g else med

            if abs(val - med) > 5.0:
                self._step_jump_count += 1
                if self._step_jump_count >= 2:
                    self._rolling_grams.clear()
                    self._rolling_grams.append(val)
                    self._spike_skip_count = 0
                    self._bitshift_skip_count = 0
                    self._step_jump_count = 0
                    return 0.0 if val < self.zero_band_g else val
            else:
                self._step_jump_count = 0

        self._spike_skip_count = 0
        self._bitshift_skip_count = 0
        self._rolling_grams.append(val)
        out = float(statistics.median(self._rolling_grams))
        return 0.0 if out < self.zero_band_g else out

    def reset_stability(self) -> None:
        """Đặt lại mốc ổn định để cho phép chu trình cân mới bắt đầu lại sạch sẽ."""
        with self._lock:
            self.is_stable = False
            self._stable_since = None
            self._history.clear()

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
            self._rolling_grams.clear()
            self._rolling_grams.append(val)
            self._spike_skip_count = 0
            self._bitshift_skip_count = 0
            self._step_jump_count = 0
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
            online = self.scale_online or getattr(self, "is_online", False)
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
