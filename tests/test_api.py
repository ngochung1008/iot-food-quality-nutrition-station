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
    mgr_filt._rolling_grams = lc_mod.deque([137.4, 137.5, 137.3, 137.4, 137.5], maxlen=5)
    mgr_filt._spike_skip_count = 0
    mgr_filt._bitshift_skip_count = 0
    assert abs(mgr_filt._apply_rolling_median_filter(276.6) - 137.4) < 0.2
    assert abs(mgr_filt._apply_rolling_median_filter(68.7) - 137.4) < 0.2
    assert len(mgr_filt._rolling_grams) == 5 and all(v < 140.0 for v in mgr_filt._rolling_grams)

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
    mgr_buf.scale_ratio = -326.1189
    mgr_buf.offset = 10000.0
    mgr_buf.calibrated = False
    mgr_buf._lock = threading.Lock()
    mgr_buf._raw_cond = threading.Condition(mgr_buf._lock)
    mgr_buf._raw_buffer = lc_mod.deque(maxlen=30)
    mgr_buf._raw_seq = 0
    mgr_buf.last_raw_timestamp = 0.0
    mgr_buf._reader_thread = threading.Thread(target=lambda: None)

    # Giả lập _reader_loop đang chạy đẩy 15 mẫu thô mới vào _raw_buffer (calibrate không gọi read_raw())
    mgr_buf.read_raw = lambda: (_ for _ in ()).throw(AssertionError("Không được gọi read_raw() trực tiếp!"))
    mgr_buf._reader_thread.is_alive = lambda: True

    def _producer_stub(base_raw):
        for i in range(18):
            _t.sleep(0.005)
            with mgr_buf._raw_cond:
                now = _t.time()
                mgr_buf._raw_buffer.append((now, base_raw + (i % 3)))
                mgr_buf._raw_seq += 1
                mgr_buf.last_raw_timestamp = now
                mgr_buf._raw_cond.notify_all()

    # Trường hợp lỗi 1: diff quá nhỏ (< 3000) -> bị từ chối, giữ nguyên -326.1189
    t1 = threading.Thread(target=_producer_stub, args=(10500.0,))
    t1.start()
    res_small = mgr_buf.calibrate_with_known_weight(500.0)
    t1.join()
    assert res_small["ok"] is False
    assert "Tín hiệu cảm biến chưa ổn định" in res_small["error"]
    assert mgr_buf.scale_ratio == -326.1189

    # Trường hợp lỗi 2: diff >= 3000 nhưng tạo scale_ratio rác = 7.7778 (< 150) -> bị từ chối!
    t2 = threading.Thread(target=_producer_stub, args=(13888.9,))  # diff=3888.9 / 500 = 7.7778
    t2.start()
    res_bad_ratio = mgr_buf.calibrate_with_known_weight(500.0)
    t2.join()
    assert res_bad_ratio["ok"] is False
    assert "Tín hiệu cảm biến chưa ổn định" in res_bad_ratio["error"]
    assert mgr_buf.scale_ratio == -326.1189

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
    mgr.auto_zero_max_g = 3.5
    mgr.auto_zero_hold_s = 3.0
    mgr._history = lc_mod.deque(maxlen=20)
    mgr._rolling_grams = lc_mod.deque(maxlen=5)
    mgr._spike_skip_count = 0
    mgr._drift_since = None
    mgr._drift_raw_samples = lc_mod.deque(maxlen=40)

    drift_adc = 10000.0 + 2.0 * mgr.scale_ratio  # lệch nhẹ 2.0g

    # Trong STABILIZING không được Auto-Zero
    mgr.station_state = "STABILIZING"
    assert mgr._track_auto_zero_drift(drift_adc, 2.0, 100.0) is False
    assert mgr._track_auto_zero_drift(drift_adc, 2.0, 104.0) is False
    assert mgr.offset == 10000.0

    # Chuyển về IDLE: giữ lệch nhẹ 2.0g trước 3.0s chưa cập nhật, đủ 3.0s phải cập nhật tare_offset -> 0.0g
    mgr.station_state = "IDLE"
    assert mgr._track_auto_zero_drift(drift_adc, 2.0, 200.0) is False
    assert mgr._track_auto_zero_drift(drift_adc, 2.1, 202.5) is False
    assert mgr.offset == 10000.0
    assert mgr._track_auto_zero_drift(drift_adc, 2.0, 203.05) is True
    assert abs(mgr.offset - drift_adc) < 50.0
    assert mgr.current_weight == 0.0

    # Nếu > 3.5g (như đặt vật thật 50g) không bao giờ Auto-Zero dù ở IDLE > 3.0s
    old_offset = mgr.offset
    assert mgr._track_auto_zero_drift(old_offset + 50.0 * mgr.scale_ratio, 50.0, 300.0) is False
    assert mgr._track_auto_zero_drift(old_offset + 50.0 * mgr.scale_ratio, 50.0, 305.0) is False
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
        client.delete(f"/api/kitchen/dishes/{dish_id}", headers=chef_hdr)
