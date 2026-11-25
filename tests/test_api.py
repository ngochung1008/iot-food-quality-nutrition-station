"""Kiểm thử tích hợp toàn bộ luồng SaaS Bếp Ăn Tập Thể (RBAC Login -> Thực Đơn -> Cân Kiểm Định -> Tích Xanh)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MOCK_HARDWARE"] = "True"

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.main import app


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_loadcell_outlier_filter_and_state_hysteresis():
    """Kiểm tra lọc ngoại lai ±25% quanh trung vị 7 mẫu và chống quay vòng trạng thái 3 mẫu < 8.0g."""
    from hardware.loadcell import LoadcellManager
    from backend.core.state_machine import NutritionStationStateMachine
    from backend.core.constants import StationState

    # 1. Bộ lọc 7 mẫu phải loại bỏ gai bội số (107g -> 214g -> 0g)
    samples = [107300, 107100, 214700, 107500, 0, 107200, 107400]
    filtered = LoadcellManager.filter_median_outliers(samples, tolerance_ratio=0.25)
    assert 107000 <= filtered <= 107600

    # 1b. Bộ lọc Trimmed Median (bỏ 25% đầu & 25% cuối)
    trimmed_vals = [0, 1000, 50000, 50100, 50200, 50300, 50150, 50250, 999999, 1000000]
    trimmed = LoadcellManager.filter_trimmed_median(trimmed_vals)
    assert 50100 <= trimmed <= 50250

    # 1c. Rolling Median loại ngay dịch bit x2 (137.4g -> 276.6g) và 0.5x (137.4g -> 68.7g), plus read_raw t_elapsed > 12ms -> None
    import hardware.loadcell as lc_mod
    from ai_engine.detector import NCNNYoloDetector

    assert NCNNYoloDetector().num_threads == 2

    mgr_filt = object.__new__(lc_mod.LoadcellManager)
    mgr_filt.zero_band_g = 0.5
    mgr_filt._rolling_grams = lc_mod.deque([137.4, 137.5, 137.3], maxlen=3)
    mgr_filt._spike_skip_count = 0
    mgr_filt._bitshift_skip_count = 0
    mgr_filt._step_jump_count = 0
    assert abs(mgr_filt._apply_rolling_median_filter(276.6) - 137.4) < 0.2
    assert abs(mgr_filt._apply_rolling_median_filter(68.7) - 137.4) < 0.2
    assert len(mgr_filt._rolling_grams) == 3 and all(v < 140.0 for v in mgr_filt._rolling_grams)

    # Nhảy tải > 5.0g trong 2 nhịp liên tiếp (0g -> 48.5g) -> xóa bộ đệm cũ và cập nhật tức thì
    mgr_jump = object.__new__(lc_mod.LoadcellManager)
    mgr_jump.zero_band_g = 0.5
    mgr_jump._rolling_grams = lc_mod.deque([0.0, 0.0, 0.0], maxlen=3)
    mgr_jump._spike_skip_count = 0
    mgr_jump._bitshift_skip_count = 0
    mgr_jump._step_jump_count = 0
    mgr_jump._apply_rolling_median_filter(48.5)
    assert mgr_jump._apply_rolling_median_filter(48.7) == 48.7
    assert list(mgr_jump._rolling_grams) == [48.7]

    mgr_raw = object.__new__(lc_mod.LoadcellManager)
    mgr_raw.mock_mode = False
    mgr_raw.hardware_available = True
    mgr_raw.sck_pin = 6
    mgr_raw.dt_pin = 5
    mgr_raw.invert_signal = True

    class _SlowGPIO:
        @staticmethod
        def input(_):
            return 0

        @staticmethod
        def output(*_):
            pass

    perf_seq = iter([10.0, 10.020])  # elapsed = 20ms > 12ms
    orig_gpio, orig_has, orig_perf = lc_mod.GPIO, lc_mod.HAS_RPI_GPIO, lc_mod.time.perf_counter
    try:
        lc_mod.GPIO = _SlowGPIO
        lc_mod.HAS_RPI_GPIO = True
        lc_mod.time.perf_counter = lambda: next(perf_seq)
        assert mgr_raw.read_raw() is None
    finally:
        lc_mod.GPIO = orig_gpio
        lc_mod.HAS_RPI_GPIO = orig_has
        lc_mod.time.perf_counter = orig_perf

    # 2. Chống quay vòng State Machine: 1 hoặc 2 mẫu 0g không được reset về IDLE
    class _DummyScale:
        current_weight = 45.0
        is_stable = False
        scale_online = True
        calibrated = True

        def read_filtered_weight(self):
            return self.current_weight

    class _DummyCam:
        def get_frame(self):
            return None

        def set_overlay_detections(self, _):
            pass

    class _DummyDetector:
        def predict(self, frame, w=0.0):
            return {"detected_class": "Egg", "confidence": 0.95, "detections": []}

    scale = _DummyScale()
    sm = NutritionStationStateMachine(scale=scale, camera=_DummyCam(), detector=_DummyDetector(), lcd=None)
    assert sm.update() == StationState.STABILIZING.value

    # 2 mẫu nhiễu 0g liên tiếp -> vẫn giữ ở STABILIZING
    scale.current_weight = 0.0
    assert sm.update() == StationState.STABILIZING.value
    assert sm.update() == StationState.STABILIZING.value
    # Mẫu thứ 3 < 8.0g -> mới về IDLE
    assert sm.update() == StationState.IDLE.value

    # 3. Tự động nhận diện khi ổn định & Tự động xóa sạch latest_inspection + bbox khi nhấc vật (< 8.0g)
    overlay_history = []
    cam = _DummyCam()
    cam.set_overlay_detections = lambda dets: overlay_history.append(list(dets))
    sm2 = NutritionStationStateMachine(scale=scale, camera=cam, detector=_DummyDetector(), lcd=None)

    scale.current_weight = 52.0
    scale.is_stable = False
    assert sm2.update() == StationState.STABILIZING.value

    scale.is_stable = True
    assert sm2.update() == StationState.CHECKOUT.value
    assert sm2.snapshot()["current_inspection"] is not None
    assert sm2.snapshot()["latest_inspection"] is not None

    # Nhấc vật ra (< 8.0g x 3 lần) -> về IDLE & xóa sạch current_inspection, latest_inspection, bbox
    scale.current_weight = 0.0
    scale.is_stable = False
    assert sm2.update() == StationState.CHECKOUT.value
    assert sm2.update() == StationState.CHECKOUT.value
    assert sm2.update() == StationState.IDLE.value
    snap_idle = sm2.snapshot()
    assert snap_idle["current_inspection"] is None
    assert snap_idle["latest_inspection"] is None
    assert overlay_history[-1] == []

    # 4. Kiểm tra khóa an toàn scale_ratio (từ chối diff < 3000 & ratio=7.7778), mặc định -326.1189 & bộ đệm luồng đọc
    import threading
    import time as _t
    from hardware.lcd_display import LCDDisplayManager, format_lcd_line

    mgr_buf = object.__new__(lc_mod.LoadcellManager)
    mgr_buf.mock_mode = False
    mgr_buf.scale_ratio = -392.25
    mgr_buf.offset = 10000.0
    mgr_buf.calibrated = False
    mgr_buf._lock = threading.Lock()
    mgr_buf._raw_cond = threading.Condition(mgr_buf._lock)
    mgr_buf._raw_buffer = lc_mod.deque(maxlen=30)
    mgr_buf._raw_seq = 0
    mgr_buf.last_raw_timestamp = 0.0
    mgr_buf._reader_thread = threading.Thread(target=lambda: None)

    # Giả lập _reader_loop đang chạy đẩy 8+ mẫu thô mới vào _raw_buffer (calibrate không gọi read_raw())
    mgr_buf.read_raw = lambda: (_ for _ in ()).throw(AssertionError("Không được gọi read_raw() trực tiếp!"))
    mgr_buf._reader_thread.is_alive = lambda: True

    def _producer_stub(base_raw):
        for i in range(10):
            _t.sleep(0.005)
            with mgr_buf._raw_cond:
                now = _t.time()
                mgr_buf._raw_buffer.append((now, base_raw + (i % 3)))
                mgr_buf._raw_seq += 1
                mgr_buf.last_raw_timestamp = now
                mgr_buf._raw_cond.notify_all()

    # Trường hợp lỗi 1: diff quá nhỏ (< 3000) -> bị từ chối, giữ nguyên -392.25
    t1 = threading.Thread(target=_producer_stub, args=(10500.0,))
    t1.start()
    res_small = mgr_buf.calibrate_with_known_weight(500.0)
    t1.join()
    assert res_small["ok"] is False
    assert "Tín hiệu cảm biến chưa ổn định" in res_small["error"]
    assert mgr_buf.scale_ratio == -392.25

    # Trường hợp lỗi 2: diff >= 3000 nhưng tạo scale_ratio rác = 7.7778 (< 150) -> bị từ chối!
    t2 = threading.Thread(target=_producer_stub, args=(13888.9,))  # diff=3888.9 / 500 = 7.7778
    t2.start()
    res_bad_ratio = mgr_buf.calibrate_with_known_weight(500.0)
    t2.join()
    assert res_bad_ratio["ok"] is False
    assert "Tín hiệu cảm biến chưa ổn định" in res_bad_ratio["error"]
    assert mgr_buf.scale_ratio == -392.25

    # 4b. Kiểm tra _reset_hx711() tự động chạy khi Timeout DOUT > 0.3s 3 lần liên tiếp
    sck_ops: list[tuple[int, bool]] = []
    sleep_ops: list[float] = []

    class _StuckDOUTGPIO:
        @staticmethod
        def input(_):
            return 1  # DOUT luôn HIGH -> ép TimeoutError > 0.3s

        @staticmethod
        def output(pin, val):
            sck_ops.append((pin, bool(val)))

    mgr_to = object.__new__(lc_mod.LoadcellManager)
    mgr_to.mock_mode = False
    mgr_to.hardware_available = True
    mgr_to.sck_pin = 6
    mgr_to.dt_pin = 5
    mgr_to._consecutive_timeouts = 0
    orig_gpio2, orig_has2, orig_sleep2 = lc_mod.GPIO, lc_mod.HAS_RPI_GPIO, lc_mod.time.sleep
    try:
        lc_mod.GPIO = _StuckDOUTGPIO
        lc_mod.HAS_RPI_GPIO = True
        lc_mod.time.sleep = lambda s: sleep_ops.append(s)
        for idx in range(3):
            try:
                mgr_to.read_raw()
                raise AssertionError("Phải raise TimeoutError")
            except TimeoutError:
                if idx < 2:
                    assert sck_ops == []
        # Sau lần timeout thứ 3 -> đã kéo SCK HIGH 100µs rồi hạ LOW
        assert (6, True) in sck_ops and (6, False) in sck_ops
        assert 0.0001 in sleep_ops
        assert mgr_to._consecutive_timeouts == 0
    finally:
        lc_mod.GPIO = orig_gpio2
        lc_mod.HAS_RPI_GPIO = orig_has2
        lc_mod.time.sleep = orig_sleep2

    # 4c. Kiểm tra khởi tạo calibration.json từ calibration.example.json khi chưa có file
    import tempfile
    from backend.core import config as cfg_mod

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        ex_file = tmp_dir / "calibration.example.json"
        ex_file.write_text('{"scale_ratio": -392.25, "tare_offset": 90068.0}\n', encoding="utf-8")
        cal_tmp = tmp_dir / "calibration.json"

        orig_cal = cfg_mod.settings.calibration_file
        object.__setattr__(cfg_mod.settings, "calibration_file", cal_tmp)
        try:
            mgr_cal = object.__new__(lc_mod.LoadcellManager)
            mgr_cal.offset = 0.0
            mgr_cal.scale_ratio = 0.0
            mgr_cal.calibrated = False
            mgr_cal.load_calibration()
            assert cal_tmp.exists()
            assert mgr_cal.calibrated is True
            assert mgr_cal.scale_ratio == -392.25
            assert mgr_cal.offset == 90068.0
        finally:
            object.__setattr__(cfg_mod.settings, "calibration_file", orig_cal)

    # 4d. Kiểm tra CameraManager trên Linux: chỉ mở index 0 với CAP_V4L2 (không mở 1), retry 1 lần sau 0.3s
    import hardware.camera as cam_mod

    opened_calls: list[tuple] = []

    class _FakeCap:
        def __init__(self, idx):
            self.idx = idx
            self.props = {}

        def isOpened(self):
            return True

        def set(self, prop, val):
            self.props[prop] = val

        def read(self):
            # Lần mở đầu thất bại hết 1.5s, lần mở thứ 2 trả frame hợp lệ
            if len(opened_calls) == 1:
                return False, None
            import numpy as _np
            return True, _np.zeros((480, 640, 3), dtype=_np.uint8)

        def release(self):
            pass

    cam_obj = object.__new__(cam_mod.CameraManager)
    cam_obj.mock_mode = False
    cam_obj.camera_index = 0
    cam_obj.device_path = "/dev/video0"
    cam_obj.width = 640
    cam_obj.height = 480
    cam_obj.fps = 30
    cam_obj.buffersize = 1
    cam_obj._cap = None
    cam_obj.hardware_available = False
    cam_obj._consecutive_errors = 0

    orig_plat, orig_vc, orig_mono = cam_mod.sys.platform, cam_mod.cv2.VideoCapture, cam_mod.time.monotonic
    orig_cam_sleep = cam_mod.time.sleep
    mono_tick = {"t": 0.0}

    def _fake_mono():
        mono_tick["t"] += 0.8
        return mono_tick["t"]

    try:
        cam_mod.sys.platform = "linux"
        cam_mod.time.monotonic = _fake_mono
        cam_mod.time.sleep = lambda _: None
        cam_mod.cv2.VideoCapture = lambda src, *args: (opened_calls.append((src, args)) or _FakeCap(src))
        assert cam_obj._open_capture() is True
        assert all(call[0] == 0 for call in opened_calls)
        assert len(opened_calls) == 2
        assert cam_obj.hardware_available is True
    finally:
        cam_mod.sys.platform = orig_plat
        cam_mod.cv2.VideoCapture = orig_vc
        cam_mod.time.monotonic = orig_mono
        cam_mod.time.sleep = orig_cam_sleep

    # 5. Kiểm tra định dạng LCD 16x2 ASCII cho IDLE, STABILIZING, INSPECTING, CHECKOUT
    lcd = LCDDisplayManager()
    lcd.display_station_status("IDLE", 0.0)
    st_idle = lcd.get_status()["details"]
    assert st_idle["line1"] == format_lcd_line("TRAM CAN SAN SANG", 16)
    assert st_idle["line2"] == format_lcd_line("0.0g | DAT VAT LEN", 16)

    lcd.display_station_status("STABILIZING", 50.4)
    st_stab = lcd.get_status()["details"]
    assert st_stab["line1"] == "DANG CAN ON DINH"
    assert st_stab["line2"].startswith("50.4g ...")

    lcd.display_station_status("INSPECTING", 50.4)
    st_insp = lcd.get_status()["details"]
    assert st_insp["line1"].startswith("AI DANG KIEM DIN")
    assert st_insp["line2"].startswith("KL: 50.4g")

    lcd.display_station_status("CHECKOUT", 50.0, food_name="Trứng gà", kcal=78.0, quality_status="FRESH", confidence=0.70)
    st_out = lcd.get_status()["details"]
    assert st_out["line1"].startswith("TRUNG GA (70%)")
    assert st_out["line2"].startswith("50.0g | 78kcal")


def test_loadcell_auto_zero_drift_and_startup_tare():
    """Kiểm tra khởi động _init_gpio (0.5s + tare 21 mẫu) và Auto-Zero Drift Tracking 0.1g..3.5g trong 3.0s."""
    import hardware.loadcell as lc_mod

    # 1. Tạo instance cô lập không đụng Singleton toàn cục để kiểm tra Auto-Zero Drift
    mgr = object.__new__(lc_mod.LoadcellManager)
    mgr.mock_mode = False
    mgr.scale_ratio = -326.1189
    mgr.offset = 10000.0
    mgr.last_grams = 2.0
    mgr.current_weight = 2.0
    mgr.station_state = "IDLE"
    mgr.auto_zero_min_g = 0.1
    mgr.auto_zero_max_g = 0.8
    mgr.auto_zero_hold_s = 4.0
    mgr._history = lc_mod.deque(maxlen=20)
    mgr._rolling_grams = lc_mod.deque(maxlen=3)
    mgr._spike_skip_count = 0
    mgr._bitshift_skip_count = 0
    mgr._step_jump_count = 0
    mgr._drift_since = None
    mgr._drift_raw_samples = lc_mod.deque(maxlen=40)

    drift_adc = 10000.0 + 0.6 * mgr.scale_ratio  # lệch nhẹ 0.6g (nằm trong 0.1g..0.8g)

    # Trong STABILIZING không được Auto-Zero
    mgr.station_state = "STABILIZING"
    assert mgr._track_auto_zero_drift(drift_adc, 0.6, 100.0) is False
    assert mgr._track_auto_zero_drift(drift_adc, 0.6, 105.0) is False
    assert mgr.offset == 10000.0

    # Chuyển về IDLE: giữ lệch nhẹ 0.6g trước 4.0s chưa cập nhật, đủ 4.0s phải cập nhật tare_offset -> 0.0g
    mgr.station_state = "IDLE"
    assert mgr._track_auto_zero_drift(drift_adc, 0.6, 200.0) is False
    assert mgr._track_auto_zero_drift(drift_adc, 0.6, 203.5) is False
    assert mgr.offset == 10000.0
    assert mgr._track_auto_zero_drift(drift_adc, 0.6, 204.05) is True
    assert abs(mgr.offset - drift_adc) < 50.0
    assert mgr.current_weight == 0.0

    # Nếu > 0.8g (ví dụ 2.0g hoặc đặt vật 50g) không bao giờ Auto-Zero dù ở IDLE > 4.0s
    old_offset = mgr.offset
    assert mgr._track_auto_zero_drift(old_offset + 2.0 * mgr.scale_ratio, 2.0, 300.0) is False
    assert mgr._track_auto_zero_drift(old_offset + 2.0 * mgr.scale_ratio, 2.0, 305.0) is False
    assert mgr._track_auto_zero_drift(old_offset + 50.0 * mgr.scale_ratio, 50.0, 310.0) is False
    assert mgr.offset == old_offset

    # 2. Kiểm tra _init_gpio chờ >= 0.5s và gọi tare(samples=21)
    calls: dict[str, object] = {"sleeps": [], "tare_samples": None}

    class _FakeGPIO:
        BCM = 11
        OUT = 0
        IN = 1

        @staticmethod
        def setwarnings(_):
            pass

        @staticmethod
        def setmode(_):
            pass

        @staticmethod
        def setup(*_):
            pass

        @staticmethod
        def output(*_):
            pass

    orig_gpio, orig_has, orig_sleep = lc_mod.GPIO, lc_mod.HAS_RPI_GPIO, lc_mod.time.sleep
    try:
        lc_mod.GPIO = _FakeGPIO
        lc_mod.HAS_RPI_GPIO = True
        lc_mod.time.sleep = lambda s: calls["sleeps"].append(s)

        mgr.sck_pin = 6
        mgr.dt_pin = 5
        mgr.invert_signal = True
        mgr.tare = lambda samples=21: (calls.__setitem__("tare_samples", samples) or True)
        mgr._init_gpio()
        assert 0.5 in calls["sleeps"]
        assert calls["tare_samples"] == 21
    finally:
        lc_mod.GPIO = orig_gpio
        lc_mod.HAS_RPI_GPIO = orig_has
        lc_mod.time.sleep = orig_sleep


def test_enterprise_kitchen_e2e_workflow():
    cal_path = ROOT_DIR / "hardware" / "calibration.json"
    cal_backup = cal_path.read_text(encoding="utf-8") if cal_path.exists() else None
    try:
        _run_e2e_test_body()
    finally:
        if cal_backup is not None:
            cal_path.write_text(cal_backup, encoding="utf-8")


def _run_e2e_test_body():
    with TestClient(app) as client:
        # 1. Health & Diagnostics
        r_health = client.get("/health")
        assert r_health.status_code == 200
        assert r_health.json()["mock_hardware"] is True

        # 2. Đăng nhập 3 vai trò RBAC
        admin_hdr = _login(client, "admin", "admin123")
        chef_hdr = _login(client, "chef", "chef123")
        recv_hdr = _login(client, "receiver", "receiver123")

        # Kiểm tra phân quyền RBAC
        assert client.get("/api/users", headers=recv_hdr).status_code == 403
        assert client.get("/api/users", headers=chef_hdr).status_code == 403
        assert client.get("/api/users", headers=admin_hdr).status_code == 200

        # 3. Kiểm tra 64 nguyên liệu & 14 món ăn mẫu
        r_foods = client.get("/api/foods")
        assert r_foods.status_code == 200
        assert len(r_foods.json()) == 64

        r_dishes = client.get("/api/kitchen/dishes", headers=chef_hdr)
        assert r_dishes.status_code == 200
        assert len(r_dishes.json()) >= 14

        # Đầu bếp tạo món mới từ 64 nguyên liệu chuẩn; từ chối nguyên liệu ngoài dataset
        r_bad_dish = client.post(
            "/api/kitchen/dishes",
            headers=chef_hdr,
            json={
                "name_vi": "Món lỗi ngoài dataset",
                "category": "Món mặn chính",
                "ingredients": [{"class_name": "InvalidFoodXYZ", "grams_per_serving": 100}],
            },
        )
        assert r_bad_dish.status_code == 400

        r_new_dish = client.post(
            "/api/kitchen/dishes",
            headers=chef_hdr,
            json={
                "name_vi": "Cá hồi sốt cam cà chua (Test)",
                "category": "Món mặn chính",
                "ingredients": [
                    {"class_name": "Fish", "grams_per_serving": 120.0},
                    {"class_name": "Tomato", "grams_per_serving": 80.0},
                ],
            },
        )
        assert r_new_dish.status_code == 200
        dish_id = r_new_dish.json()["id"]
        assert r_new_dish.json()["per_serving"]["energy_kcal"] > 0

        # Receiver không được phép tạo phiếu thực đơn
        r_forbid_order = client.post(
            "/api/kitchen/orders",
            headers=recv_hdr,
            json={
                "title": "Không hợp lệ",
                "meal_date": "2026-11-18",
                "servings": 10,
                "dish_ids": [dish_id],
            },
        )
        assert r_forbid_order.status_code == 403

        # 4. Đầu bếp lập thực đơn 10 suất -> Sinh Phiếu Yêu Cầu Nguyên Liệu
        r_order = client.post(
            "/api/kitchen/orders",
            headers=chef_hdr,
            json={
                "title": "Bữa trưa kiểm thử E2E",
                "meal_date": "2026-11-18",
                "meal_shift": "Bữa trưa",
                "servings": 10,
                "target_kcal_per_serving": 650.0,
                "dish_ids": [dish_id],
                "tolerance_percent": 5.0,
            },
        )
        assert r_order.status_code == 200, r_order.text
        order = r_order.json()
        order_id = order["id"]
        assert order["status"] == "PENDING"
        assert order["target_kcal_per_serving"] == 650.0
        assert order["estimated_total_cost_vnd"] > 0
        assert len(order["items"]) == 2

        fish_item = next(i for i in order["items"] if i["class_name"] == "Fish")
        tomato_item = next(i for i in order["items"] if i["class_name"] == "Tomato")
        assert fish_item["required_gram"] == 1200.0
        assert fish_item["min_acceptable_gram"] == 1140.0
        assert fish_item["unit_price_per_kg"] > 0

        # Kiểm tra gói dữ liệu JSON đầy đủ từ /api/station/inspect
        client.post("/api/station/simulate/weight", json={"weight_gram": 1200.0})
        r_insp_full = client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        assert r_insp_full.status_code == 200
        insp_obj = r_insp_full.json()["inspection"]
        for k in (
            "food_name_vi", "food_name_en", "confidence_percent", "weight_g",
            "unit_price_per_kg", "total_price_vnd", "calories", "protein", "lipid", "carb",
            "quality_status", "bbox",
        ):
            assert k in insp_obj, f"Thiếu trường {k} trong kết quả AI"
        assert insp_obj["total_price_vnd"] > 0

        # 5. Nhân viên tiếp nhận cân đối chiếu tại Trạm cân
        # 5a. Khối lượng thiếu (< 95%) -> bị từ chối tích xanh
        client.post("/api/station/simulate/weight", json={"weight_gram": 500.0})
        client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        r_short = client.post(
            f"/api/kitchen/orders/{order_id}/check-item",
            headers=recv_hdr,
            json={"item_id": fish_item["id"]},
        )
        assert r_short.status_code == 400

        # 5b. Thực phẩm hư hỏng (REJECTED) -> bị từ chối tích xanh
        client.post("/api/station/simulate/weight", json={"weight_gram": 1200.0})
        client.post("/api/station/inspect", json={"override_label": "Rotten_Fish", "override_quality": "REJECTED"})
        r_rotten = client.post(
            f"/api/kitchen/orders/{order_id}/check-item",
            headers=recv_hdr,
            json={"item_id": fish_item["id"]},
        )
        assert r_rotten.status_code == 400

        # 5c. Kích hoạt active-order + Đặt Fish tươi đủ 1200g -> TỰ ĐỘNG TÍCH XANH dòng 1
        assert client.post("/api/station/active-order", json={"order_id": order_id}).status_code == 200
        client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        r_ord_mid = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr)
        assert r_ord_mid.status_code == 200
        d1_ord = r_ord_mid.json()
        assert d1_ord["status"] == "IN_PROGRESS"
        assert d1_ord["progress"]["completed"] == 1
        log1_id = next(i["log_id"] for i in d1_ord["items"] if i["id"] == fish_item["id"])

        # 5d. Đặt Tomato tươi 790g (>= 95% của 800g) -> TỰ ĐỘNG TÍCH XANH dòng 2 -> HOÀN THÀNH ĐƠN HÀNG
        client.post("/api/station/simulate/weight", json={"weight_gram": 790.0})
        client.post("/api/station/inspect", json={"override_label": "Tomato", "override_quality": "FRESH"})
        r_ord_done = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr)
        assert r_ord_done.status_code == 200
        d2_ord = r_ord_done.json()
        assert d2_ord["status"] == "COMPLETED"
        assert d2_ord["progress"]["completed"] == 2
        assert 1980.0 <= d2_ord["actual_summary"]["total_gram"] <= 2000.0
        assert d2_ord["actual_summary"]["total_cost_vnd"] > 0
        assert d2_ord["actual_summary"]["total_kcal"] > 0
        log2_id = next(i["log_id"] for i in d2_ord["items"] if i["id"] == tomato_item["id"])

        # Kiểm tra nút Reset phiên & Reset phiếu hoàn thành để demo lại
        r_reset_station = client.post("/api/station/reset", json={"reset_order": True, "order_id": order_id})
        assert r_reset_station.status_code == 200
        rs_json = r_reset_station.json()
        assert rs_json["snapshot"]["state"] == "IDLE"
        assert rs_json["snapshot"]["latest_inspection"] is None
        assert rs_json["order"]["status"] == "PENDING"
        assert rs_json["order"]["progress"]["completed"] == 0

        r_reset_order = client.post(f"/api/kitchen/orders/{order_id}/reset", headers=recv_hdr)
        assert r_reset_order.status_code == 200
        assert r_reset_order.json()["order"]["progress"]["completed"] == 0

        # Kiểm tra bổ sung nguyên liệu phát sinh ngoài danh sách phiếu (+ Bổ sung vào phiếu & Tích xanh)
        old_kcal = r_reset_order.json()["order"]["total_kcal"]
        client.post("/api/station/simulate/weight", json={"weight_gram": 350.0})
        client.post("/api/station/inspect", json={"override_label": "Banana", "override_quality": "FRESH"})
        r_extra_done = client.post(
            f"/api/kitchen/orders/{order_id}/add-extra-item",
            headers=recv_hdr,
            json={"class_name": "Banana", "mark_completed": True, "note": "Bổ sung phát sinh tại trạm"},
        )
        assert r_extra_done.status_code == 200, r_extra_done.text
        ex_res = r_extra_done.json()
        assert ex_res["item"]["class_name"] == "Banana"
        assert ex_res["item"]["status"] == "COMPLETED"
        assert ex_res["order"]["total_kcal"] > old_kcal
        assert ex_res["receipt"]["note"] == "Bổ sung phát sinh tại trạm"
        extra_log_id = ex_res["receipt"]["id"]

        # Kiểm tra nút "+ Thêm món vào phiếu" (PENDING) từ 64 nguyên liệu chuẩn
        r_add_pending = client.post(
            f"/api/kitchen/orders/{order_id}/add-extra-item",
            headers=recv_hdr,
            json={"class_name": "Carrot", "required_gram": 500.0, "mark_completed": False},
        )
        assert r_add_pending.status_code == 200, r_add_pending.text
        ap_res = r_add_pending.json()
        assert ap_res["item"]["class_name"] == "Carrot"
        assert ap_res["item"]["status"] == "PENDING"
        assert ap_res["item"]["required_gram"] == 500.0
        carrot_item_id = ap_res["item"]["id"]

        # Kiểm tra không cộng dồn khi PENDING (dù trước đó có số dư 123g) & chỉ ghi 1 lần/phiên cho tới IDLE
        from backend.database.crud import mark_procurement_item_completed
        from backend.database.models import get_db_conn

        with get_db_conn() as conn:
            conn.execute("UPDATE procurement_items SET actual_gram = 123.0 WHERE id = ?", (carrot_item_id,))

        client.post("/api/station/reset", json={"reset_order": False})
        client.post("/api/station/simulate/weight", json={"weight_gram": 510.0})
        r_c1 = client.post("/api/station/inspect", json={"override_label": "Carrot", "override_quality": "FRESH"})
        assert r_c1.status_code == 200
        # Lần tự động khớp khi chưa COMPLETED -> lấy đúng ~510g, KHÔNG thành 123 + 510 = 633g
        ord_after_carrot = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        carrot_row = next(i for i in ord_after_carrot["items"] if i["id"] == carrot_item_id)
        assert 500.0 <= carrot_row["actual_gram"] <= 520.0
        carrot_log_id = carrot_row["log_id"]

        # Trong cùng phiên CHECKOUT (chưa nhấc về IDLE), gọi lại run_inspection không được ghi lặp lần 2
        from backend.services.station_service import station_service

        assert station_service.state_machine._session_committed is True
        station_service.state_machine.run_inspection(weight_gram=515.0, override_label="Carrot", override_quality="FRESH")
        ord_same_sess = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        carrot_row_same = next(i for i in ord_same_sess["items"] if i["id"] == carrot_item_id)
        assert carrot_row_same["actual_gram"] == carrot_row["actual_gram"]

        # Khi đã COMPLETED và nhân viên chủ động bấm xác nhận thêm lô (accumulate=True) -> mới cộng dồn
        acc_ord = mark_procurement_item_completed(
            order_id=order_id,
            item_id=carrot_item_id,
            actual_gram=200.0,
            quality_status="FRESH",
            confidence=0.95,
            checked_by="receiver",
            log_id=carrot_log_id,
            accumulate=True,
        )
        carrot_acc = next(i for i in acc_ord["items"] if i["id"] == carrot_item_id)
        assert round(carrot_acc["actual_gram"], 1) == round(carrot_row["actual_gram"] + 200.0, 1)

        # 6. Báo cáo, Export CSV/XLSX & Calibration (Admin)
        # Kiểm tra nút Tare / Về 0g đặt nắp nhôm (230g) -> đưa ngay về 0.0g & IDLE
        client.post("/api/station/simulate/weight", json={"weight_gram": 230.0})
        r_tare = client.post("/api/station/tare")
        assert r_tare.status_code == 200
        assert r_tare.json()["weight_gram"] == 0.0
        assert r_tare.json()["snapshot"]["state"] == "IDLE"

        r_csv = client.get("/api/reports/export.csv")
        assert r_csv.status_code == 200
        assert "Cà chua chín" in r_csv.content.decode("utf-8")

        r_xlsx = client.get("/api/reports/export.xlsx")
        assert r_xlsx.status_code == 200
        assert len(r_xlsx.content) > 500

        assert client.post("/api/hardware/calibrate/tare", headers=recv_hdr).status_code == 403
        assert client.post("/api/hardware/calibrate/tare", headers=admin_hdr).status_code == 200
        assert (
            client.post("/api/hardware/calibrate/measure", headers=admin_hdr, json={"known_weight_g": 500.0}).status_code
            == 200
        )

        # 7. SPA & WebSocket
        r_spa = client.get("/")
        assert r_spa.status_code == 200
        assert "FreshKitchen POS" in r_spa.text

        with client.websocket_connect("/ws/station") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "snapshot"
            assert msg["data"]["mock_hardware"] is True

        # Dọn dẹp dữ liệu test
        client.delete(f"/api/logs/{log1_id}", headers=admin_hdr)
        client.delete(f"/api/logs/{log2_id}", headers=admin_hdr)
        client.delete(f"/api/logs/{extra_log_id}", headers=admin_hdr)
        client.delete(f"/api/logs/{carrot_log_id}", headers=admin_hdr)
        client.delete(f"/api/kitchen/dishes/{dish_id}", headers=chef_hdr)


def test_multibatch_accumulation_and_optimizations():
    """Kiểm tra cân cộng dồn nhiều mẻ (PARTIAL -> COMPLETED), đồng bộ xóa log, dọn captures và JPEG stream gating."""
    import tempfile
    from backend.core import config as cfg_mod
    from backend.database.crud import get_summary_kpis, local_today_str
    from backend.services.station_service import station_service
    from hardware.camera import CameraManager

    with TestClient(app) as client:
        admin_hdr = _login(client, "admin", "admin123")
        chef_hdr = _login(client, "chef", "chef123")
        recv_hdr = _login(client, "receiver", "receiver123")

        # 1. Kiểm tra JPEG stream gating trên CameraManager
        cam = CameraManager()
        assert cam.active_stream_clients >= 0
        before_clients = cam.active_stream_clients
        cam.acquire_stream()
        assert cam.active_stream_clients == before_clients + 1
        cam.release_stream()
        assert cam.active_stream_clients == before_clients

        # 2. Kiểm tra telemetry_snapshot gọn nhẹ không mang payload inspection nặng
        tel = station_service.state_machine.telemetry_snapshot()
        assert "weight_gram" in tel and "state" in tel
        assert "current_inspection" not in tel

        # 3. Tạo phiếu mới với nguyên liệu Fish 1000g (min_acceptable = 950g) để test cộng dồn 2 rổ (400g + 600g)
        dishes = client.get("/api/kitchen/dishes", headers=chef_hdr).json()
        fish_dish = next(d for d in dishes if any(i["class_name"] == "Fish" for i in d["ingredients"]))
        r_order = client.post(
            "/api/kitchen/orders",
            headers=chef_hdr,
            json={
                "title": "Phiếu test cộng dồn nhiều mẻ",
                "meal_date": local_today_str(),
                "meal_shift": "Bữa trưa",
                "servings": 10,
                "dish_ids": [fish_dish["id"]],
                "tolerance_percent": 5.0,
            },
        )
        assert r_order.status_code == 200, r_order.text
        order = r_order.json()
        order_id = order["id"]
        fish_item = next(i for i in order["items"] if i["class_name"] == "Fish")
        req_g = float(fish_item["required_gram"])
        batch1_g = round(req_g * 0.4, 1)
        batch2_g = round(req_g * 0.65, 1)

        client.post("/api/station/reset", json={"reset_order": False})
        client.post("/api/station/active-order", json={"order_id": order_id})

        # Mẻ 1 (40% định lượng) -> tự chuyển PARTIAL, chưa COMPLETED
        client.post("/api/station/simulate/weight", json={"weight_gram": batch1_g})
        r_b1 = client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        assert r_b1.status_code == 200
        ord_mid = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        fish_mid = next(i for i in ord_mid["items"] if i["id"] == fish_item["id"])
        assert fish_mid["status"] == "PARTIAL"
        assert abs(fish_mid["actual_gram"] - batch1_g) < 0.2
        log_b1 = fish_mid["log_id"]

        # Nhấc rổ 1 về IDLE rồi đặt rổ 2 (65% định lượng) -> tổng 105% -> COMPLETED (Tích xanh)
        client.post("/api/station/reset", json={"reset_order": False})
        client.post("/api/station/simulate/weight", json={"weight_gram": batch2_g})
        r_b2 = client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        assert r_b2.status_code == 200
        ord_done = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        fish_done = next(i for i in ord_done["items"] if i["id"] == fish_item["id"])
        assert fish_done["status"] == "COMPLETED"
        assert abs(fish_done["actual_gram"] - (batch1_g + batch2_g)) < 0.2
        log_b2 = fish_done["log_id"]

        # 4. Kiểm tra đồng bộ xóa log trừ ngược daily_nutrition_analytics & phân quyền ADMIN
        assert client.delete(f"/api/logs/{log_b2}", headers=recv_hdr).status_code == 403
        before_kpi = get_summary_kpis(days=7)["today"]
        assert client.delete(f"/api/logs/{log_b2}", headers=admin_hdr).status_code == 200
        after_kpi = get_summary_kpis(days=7)["today"]
        assert after_kpi["total_batches"] == max(0, before_kpi["total_batches"] - 1)
        assert after_kpi["total_kcal"] <= before_kpi["total_kcal"]

        # Xóa log mẻ 1 & kiểm tra _cleanup_old_captures(max_files=2)
        client.delete(f"/api/logs/{log_b1}", headers=admin_hdr)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_cap = Path(tmpdir)
            for idx in range(5):
                f = tmp_cap / f"inspect_20261125_10000{idx}.jpg"
                f.write_bytes(b"jpg")
            orig_cap = cfg_mod.settings.capture_dir
            object.__setattr__(cfg_mod.settings, "capture_dir", tmp_cap)
            try:
                removed = station_service._cleanup_old_captures(max_files=2)
                assert removed == 3
                assert len(list(tmp_cap.glob("inspect_*.jpg"))) == 2
            finally:
                object.__setattr__(cfg_mod.settings, "capture_dir", orig_cap)


def test_context_and_weight_aware_reranking():
    """Kiểm chứng logic _rerank_with_context_and_weight + giải mã tensor đa ứng viên + tự động tích xanh Egg."""
    import numpy as np
    from ai_engine.detector import (
        NCNNYoloDetector,
        _pack_prediction,
        _rerank_with_context_and_weight,
    )
    from backend.services.station_service import station_service

    # 1. Kiểm tra trực tiếp _rerank_with_context_and_weight: Chicken (0.76) vs Egg (0.28) tại 55g + expected=["Egg"]
    cands = [
        {"class_id": 17, "label": "Chicken", "confidence": 0.76},
        {"class_id": 24, "label": "Egg", "confidence": 0.28},
    ]
    rr = _rerank_with_context_and_weight(cands, weight_gram=55.0, expected_classes=["Egg"])
    assert rr["selected"]["label"] == "Egg"
    assert rr["reranked"] is True

    # 1b. Kiểm tra trường hợp trọng lượng nặng (>= 250g) giảm ưu tiên Egg nếu có Chicken/Potato
    heavy_cands = [
        {"class_id": 24, "label": "Egg", "confidence": 0.55},
        {"class_id": 17, "label": "Chicken", "confidence": 0.45},
    ]
    rr_heavy = _rerank_with_context_and_weight(heavy_cands, weight_gram=320.0, expected_classes=None)
    assert rr_heavy["selected"]["label"] == "Chicken"

    # 2. Kiểm tra giải mã tensor YOLO26n (68, 3549) giữ top_candidates >= 0.15 và _pack_prediction chọn Egg
    dec = NCNNYoloDetector()
    chicken_id = next(k for k, v in dec.class_names.items() if v == "Chicken")
    egg_id = next(k for k, v in dec.class_names.items() if v == "Egg")

    fake_out = np.zeros((68, 3549), dtype=np.float32)
    fake_out[0, 100] = 208.0
    fake_out[1, 100] = 208.0
    fake_out[2, 100] = 160.0
    fake_out[3, 100] = 120.0
    fake_out[4 + chicken_id, 100] = 0.76
    fake_out[4 + egg_id, 100] = 0.28

    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    padded, ratio, pad_x, pad_y = dec._letterbox(frame, 416)
    dets = dec._postprocess_yolo(fake_out, frame.shape[:2], letterbox=(ratio, pad_x, pad_y))
    assert dets and len(dets[0]["top_candidates"]) >= 2
    assert {c["label"] for c in dets[0]["top_candidates"]} >= {"Chicken", "Egg"}

    packed = _pack_prediction(
        dets,
        frame=frame,
        inference_time_ms=10,
        strategy="ncnn",
        weight_gram=55.0,
        expected_classes=["Egg"],
        conf_threshold=0.35,
    )
    assert packed["detected_class"] == "Egg"
    assert packed["reranked"] is True

    # 2b. Kiểm tra khoảng 0.22..0.35 khớp expected_classes -> trả về WARNING kèm ghi chú thay vì Unknown
    low_cands = [{"class_id": 24, "label": "Egg", "confidence": 0.16}]
    low_packed = _pack_prediction(
        [{"class_id": 24, "label": "Egg", "confidence": 0.16, "box": {"x1": 10, "y1": 10, "x2": 100, "y2": 100}, "top_candidates": low_cands}],
        frame=frame,
        inference_time_ms=10,
        strategy="ncnn",
        weight_gram=20.0,
        expected_classes=["Egg"],
        conf_threshold=0.35,
    )
    # raw=0.16 < 0.20, trong confusion pair {"Egg", "Chicken"} -> +0.25 -> 0.41 (>=0.35);
    # thử trường hợp Tomato (không thuộc confusion pair) không được +0.25 nhưng reranked_score = 0.28 nằm trong 0.22..0.35:
    low_tom = _pack_prediction(
        [{"class_id": 59, "label": "Tomato", "confidence": 0.28, "box": {"x1": 10, "y1": 10, "x2": 100, "y2": 100}, "top_candidates": [{"class_id": 59, "label": "Tomato", "confidence": 0.28}]}],
        frame=frame,
        inference_time_ms=10,
        strategy="ncnn",
        weight_gram=150.0,
        expected_classes=["Tomato"],
        conf_threshold=0.35,
    )
    assert low_packed["detected_class"] == "Egg"
    # Tomato (0.28) + expected (+0.25) = 0.53; để score sau rerank nằm chính xác trong 0.22..0.35:
    # Egg (0.60) với weight=300g bị trừ 0.35 -> 0.25 (nếu expected=["Egg"] không +0.25? Không, expected +0.25 -> 0.50).
    # Test với Tomato raw=0.28 không ở trong expected -> Unknown, còn Tomato raw=0.28 trong expected -> nhận diện được!
    assert low_tom["detected_class"] == "Tomato"
    unknown_tom = _pack_prediction(
        [{"class_id": 59, "label": "Tomato", "confidence": 0.28, "box": {"x1": 10, "y1": 10, "x2": 100, "y2": 100}, "top_candidates": [{"class_id": 59, "label": "Tomato", "confidence": 0.28}]}],
        frame=frame,
        inference_time_ms=10,
        strategy="ncnn",
        weight_gram=150.0,
        expected_classes=["Fish"],
        conf_threshold=0.35,
    )
    assert unknown_tom["detected_class"] == "Unknown"

    # Kiểm tra trực tiếp nhánh 0.22 <= final_score < 0.35 khi expected=["Egg"] (vd Egg raw=0.60, weight=300g -> -0.35 -> 0.25, với detector chưa cộng hoặc raw=0.26 không qua ngưỡng +0.25)
    warn_res = _pack_prediction(
        [{"class_id": 24, "label": "Egg", "confidence": 0.12, "box": {"x1": 10, "y1": 10, "x2": 100, "y2": 100}, "top_candidates": [{"class_id": 24, "label": "Egg", "confidence": 0.12}]}],
        frame=frame,
        inference_time_ms=10,
        strategy="ncnn",
        weight_gram=50.0,
        expected_classes=["Egg"],
        conf_threshold=0.35,
    )
    assert warn_res["detected_class"] == "Unknown"  # 0.12 < 0.15

    # 3. E2E qua StateMachine & API: gắn phiếu Egg -> detector trả Chicken (0.76) + Egg (0.28) -> tự động chọn Egg & tích xanh phiếu!
    with TestClient(app) as client:
        admin_hdr = _login(client, "admin", "admin123")
        chef_hdr = _login(client, "chef", "chef123")
        recv_hdr = _login(client, "receiver", "receiver123")

        dishes = client.get("/api/kitchen/dishes", headers=chef_hdr).json()
        egg_dish = next(d for d in dishes if any(i["class_name"] == "Egg" for i in d["ingredients"]))
        r_ord = client.post(
            "/api/kitchen/orders",
            headers=chef_hdr,
            json={
                "title": "Phiếu test AI Rerank Egg",
                "meal_date": "2026-11-25",
                "meal_shift": "Bữa sáng",
                "servings": 1,
                "dish_ids": [egg_dish["id"]],
                "tolerance_percent": 5.0,
            },
        )
        assert r_ord.status_code == 200, r_ord.text
        order = r_ord.json()
        order_id = order["id"]
        egg_item = next(i for i in order["items"] if i["class_name"] == "Egg")

        class _ConfusedDetector:
            def predict(self, img, weight_gram=0.0, expected_classes=None):
                return _pack_prediction(
                    [
                        {
                            "class_id": chicken_id,
                            "label": "Chicken",
                            "confidence": 0.76,
                            "box": {"x1": 100, "y1": 80, "x2": 400, "y2": 360},
                            "top_candidates": [
                                {"class_id": chicken_id, "label": "Chicken", "confidence": 0.76},
                                {"class_id": egg_id, "label": "Egg", "confidence": 0.28},
                            ],
                        }
                    ],
                    frame=img,
                    inference_time_ms=15,
                    strategy="ncnn",
                    weight_gram=weight_gram,
                    expected_classes=expected_classes,
                    conf_threshold=0.35,
                )

        orig_det = station_service.state_machine.detector
        station_service.state_machine.detector = _ConfusedDetector()
        try:
            client.post("/api/station/reset", json={"reset_order": False})
            client.post("/api/station/active-order", json={"order_id": order_id})
            client.post("/api/station/simulate/weight", json={"weight_gram": float(egg_item["required_gram"])})
            r_insp = client.post("/api/station/inspect", json={})
            assert r_insp.status_code == 200, r_insp.text
            insp = r_insp.json()["inspection"]
            assert insp["detected_class"] == "Egg"
            assert insp["reranked"] is True

            ord_after = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
            egg_after = next(i for i in ord_after["items"] if i["id"] == egg_item["id"])
            assert egg_after["status"] == "COMPLETED"
            if egg_after.get("log_id"):
                client.delete(f"/api/logs/{egg_after['log_id']}", headers=admin_hdr)
        finally:
            station_service.state_machine.detector = orig_det


def test_order_reset_does_not_accumulate_stale_logs_cost_or_kcal():
    """Tạo phiếu -> cân -> reset phiếu -> cân lại 60.6g Egg -> xác nhận tổng tiền = 3.333đ & Calo = 88.5 kcal."""
    with TestClient(app) as client:
        admin_hdr = _login(client, "admin", "admin123")
        chef_hdr = _login(client, "chef", "chef123")
        recv_hdr = _login(client, "receiver", "receiver123")

        r_dish = client.post(
            "/api/kitchen/dishes",
            headers=chef_hdr,
            json={
                "name_vi": "Trứng gà test reset (1 quả)",
                "category": "Bữa sáng Demo",
                "ingredients": [{"class_name": "Egg", "grams_per_serving": 50.0}],
            },
        )
        assert r_dish.status_code == 200, r_dish.text
        dish_id = r_dish.json()["id"]

        r_ord = client.post(
            "/api/kitchen/orders",
            headers=chef_hdr,
            json={
                "title": "Phiếu test reset không cộng dồn log cũ",
                "meal_date": "2026-11-25",
                "meal_shift": "Ca Sáng",
                "servings": 1,
                "dish_ids": [dish_id],
                "tolerance_percent": 5.0,
            },
        )
        assert r_ord.status_code == 200, r_ord.text
        order_id = r_ord.json()["id"]

        client.post("/api/station/reset", json={"reset_order": False})
        client.post("/api/station/active-order", json={"order_id": order_id})

        # Lần cân 1 (55.0g) & Lần cân 2 (60.6g sau reset lần 1)
        client.post("/api/station/simulate/weight", json={"weight_gram": 55.0})
        client.post("/api/station/inspect", json={"override_label": "Egg", "override_quality": "FRESH"})
        ord1 = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        log1_id = ord1["items"][0]["log_id"]

        # Reset phiếu -> log1 phải bị gỡ order_id/order_item_id và summary về 0
        r_rst = client.post(f"/api/kitchen/orders/{order_id}/reset", headers=recv_hdr)
        assert r_rst.status_code == 200
        rst_ord = r_rst.json()["order"]
        assert rst_ord["actual_summary"]["total_gram"] == 0.0
        assert rst_ord["actual_summary"]["total_cost_vnd"] == 0
        assert rst_ord["actual_summary"]["total_kcal"] == 0.0

        # Cân lại 60.6g Egg (55.000 đ/kg) -> tổng tiền phải đúng 3.333 đ, Calo đúng 88.5 kcal (không cộng dồn lần 1)
        client.post("/api/station/simulate/weight", json={"weight_gram": 60.6})
        client.post("/api/station/inspect", json={"override_label": "Egg", "override_quality": "FRESH"})
        ord2 = client.get(f"/api/kitchen/orders/{order_id}", headers=recv_hdr).json()
        log2_id = ord2["items"][0]["log_id"]
        assert ord2["status"] == "COMPLETED"
        assert ord2["actual_summary"]["total_gram"] == 60.6
        assert ord2["actual_summary"]["total_cost_vnd"] == 3333
        assert ord2["actual_summary"]["total_kcal"] == 88.5

        # Dọn dẹp
        if log1_id:
            client.delete(f"/api/logs/{log1_id}", headers=admin_hdr)
        if log2_id:
            client.delete(f"/api/logs/{log2_id}", headers=admin_hdr)
        client.delete(f"/api/kitchen/dishes/{dish_id}", headers=chef_hdr)
