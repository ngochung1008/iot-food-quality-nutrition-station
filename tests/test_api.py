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
        log2_id = next(i["log_id"] for i in d2_ord["items"] if i["id"] == tomato_item["id"])

        # 6. Báo cáo, Export CSV/XLSX & Calibration (Admin)
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
        client.delete(f"/api/kitchen/dishes/{dish_id}", headers=chef_hdr)
