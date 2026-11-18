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


def test_enterprise_kitchen_e2e_workflow():
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
                "dish_ids": [dish_id],
                "tolerance_percent": 5.0,
            },
        )
        assert r_order.status_code == 200, r_order.text
        order = r_order.json()
        order_id = order["id"]
        assert order["status"] == "PENDING"
        assert len(order["items"]) == 2

        fish_item = next(i for i in order["items"] if i["class_name"] == "Fish")
        tomato_item = next(i for i in order["items"] if i["class_name"] == "Tomato")
        assert fish_item["required_gram"] == 1200.0
        assert fish_item["min_acceptable_gram"] == 1140.0

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

        # 5c. Đặt Fish tươi đủ 1200g -> Tích xanh dòng 1 (Đơn chuyển IN_PROGRESS)
        client.post("/api/station/inspect", json={"override_label": "Fish", "override_quality": "FRESH"})
        r_ok1 = client.post(
            f"/api/kitchen/orders/{order_id}/check-item",
            headers=recv_hdr,
            json={"item_id": fish_item["id"]},
        )
        assert r_ok1.status_code == 200, r_ok1.text
        d1 = r_ok1.json()
        assert d1["order"]["status"] == "IN_PROGRESS"
        assert d1["order"]["progress"]["completed"] == 1
        log1_id = d1["receipt"]["id"]

        # 5d. Đặt Tomato tươi 790g (nằm trong ngưỡng >= 95% của 800g = 760g) -> Tích xanh dòng 2 -> HOÀN THÀNH ĐƠN HÀNG
        client.post("/api/station/simulate/weight", json={"weight_gram": 790.0})
        client.post("/api/station/inspect", json={"override_label": "Tomato", "override_quality": "FRESH"})
        r_ok2 = client.post(
            f"/api/kitchen/orders/{order_id}/check-item",
            headers=recv_hdr,
            json={"item_id": tomato_item["id"]},
        )
        assert r_ok2.status_code == 200, r_ok2.text
        d2 = r_ok2.json()
        assert d2["order"]["status"] == "COMPLETED"
        assert d2["order"]["progress"]["completed"] == 2
        log2_id = d2["receipt"]["id"]

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
        assert "FreshKitchen AI" in r_spa.text

        with client.websocket_connect("/ws/station") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "snapshot"
            assert msg["data"]["mock_hardware"] is True

        # Dọn dẹp dữ liệu test
        client.delete(f"/api/logs/{log1_id}", headers=admin_hdr)
        client.delete(f"/api/logs/{log2_id}", headers=admin_hdr)
        client.delete(f"/api/kitchen/dishes/{dish_id}", headers=chef_hdr)
