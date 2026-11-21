"""Thao tác CRUD SQLite: Người dùng (RBAC), 64 thực phẩm chuẩn, Món ăn, Phiếu chuẩn bị & Nhật ký."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ai_engine.nutrition_mapper import NUTRITION_TABLE_64, normalize_label
from backend.core.security import ROLE_ADMIN, ROLE_CHEF, ROLE_RECEIVER, hash_password
from backend.database.models import SCHEMA_SQL, get_db_conn

logger = logging.getLogger("nutrition_station.database.crud")

# Bộ 14 món ăn mẫu cho bếp ăn tập thể — 100% nguyên liệu thuộc 64 classes YOLO26n
SEED_DISHES: list[dict[str, Any]] = [
    {
        "code": "DISH_FISH_PASSION",
        "name_vi": "Cá phi lê áp chảo sốt chanh leo",
        "category": "Món mặn chính",
        "description": "Cá phi lê giàu đạm kết hợp măng tây và sốt chanh leo tươi.",
        "ingredients": [("Fish", 150.0), ("Passion Fruit", 35.0), ("Asparagus", 60.0), ("Lemon", 10.0)],
    },
    {
        "code": "DISH_BEEF_CAULIFLOWER",
        "name_vi": "Thịt bò xào súp lơ & ớt chuông",
        "category": "Món mặn chính",
        "description": "Thịt bò nạc xào súp lơ trắng, ớt chuông giòn ngọt.",
        "ingredients": [("Beef", 130.0), ("Cauliflower", 100.0), ("Bell Pepper", 50.0), ("Garlic", 8.0)],
    },
    {
        "code": "DISH_CHICKEN_CABBAGE",
        "name_vi": "Thịt gà luộc xé phay gỏi bắp cải",
        "category": "Món mặn chính",
        "description": "Thịt gà luộc trộn bắp cải trắng, cà rốt và chanh tươi.",
        "ingredients": [("Chicken", 160.0), ("Cabbage", 90.0), ("Carrot", 40.0), ("Lime", 15.0)],
    },
    {
        "code": "DISH_SHRIMP_ZUCCHINI_SOUP",
        "name_vi": "Canh bí ngòi nấu tôm tươi",
        "category": "Món canh",
        "description": "Canh thanh mát từ bí ngòi xanh, tôm tươi và cà chua.",
        "ingredients": [("Zucchini", 120.0), ("Shrimp", 80.0), ("Tomato", 40.0), ("Red Onion", 10.0)],
    },
    {
        "code": "DISH_SALAD_TOMATO_EGG",
        "name_vi": "Salad cà chua dưa chuột trứng gà",
        "category": "Món rau / Salad",
        "description": "Salad thanh đạm cung cấp vitamin C và đạm từ trứng gà.",
        "ingredients": [("Tomato", 90.0), ("Cucumber", 90.0), ("Egg", 60.0), ("White Onion", 20.0)],
    },
    {
        "code": "DISH_PORK_BRAISED_EGG",
        "name_vi": "Thịt heo kho trứng & cà rốt",
        "category": "Món mặn chính",
        "description": "Thịt lợn nạc kho trứng gà cùng cà rốt củ.",
        "ingredients": [("Pork", 140.0), ("Egg", 60.0), ("Carrot", 60.0), ("Garlic", 8.0)],
    },
    {
        "code": "DISH_BEEF_POTATO_STEW",
        "name_vi": "Bò hầm khoai tây cà rốt",
        "category": "Món mặn chính",
        "description": "Món hầm giàu năng lượng cho ca làm việc nặng.",
        "ingredients": [("Beef", 130.0), ("Potato", 120.0), ("Carrot", 70.0), ("Tomato", 50.0)],
    },
    {
        "code": "DISH_CHICKEN_MUSHROOM",
        "name_vi": "Gà xào nấm tươi & đậu cô ve",
        "category": "Món mặn chính",
        "description": "Thịt gà xào nấm và đậu cô ve giữ độ giòn tự nhiên.",
        "ingredients": [("Chicken", 140.0), ("Mushroom", 70.0), ("Green Beans", 80.0), ("Ginger", 8.0)],
    },
    {
        "code": "DISH_STEAMED_FISH_GINGER",
        "name_vi": "Cá hấp gừng hành tây & cà chua",
        "category": "Món mặn chính",
        "description": "Cá hấp giữ trọn dưỡng chất, ít chất béo bão hòa.",
        "ingredients": [("Fish", 160.0), ("Ginger", 15.0), ("White Onion", 40.0), ("Tomato", 60.0)],
    },
    {
        "code": "DISH_CRAB_CORN_SOUP",
        "name_vi": "Cua biển nấu bắp ngọt & bí ngòi",
        "category": "Món canh",
        "description": "Món canh hải sản giàu canxi và kẽm.",
        "ingredients": [("Crab", 150.0), ("Corn", 80.0), ("Zucchini", 70.0), ("Lemon", 15.0)],
    },
    {
        "code": "DISH_PORK_EGGPLANT",
        "name_vi": "Thịt heo xào cà tím & ớt chuông",
        "category": "Món mặn chính",
        "description": "Thịt lợn nạc xào cà tím và ớt chuông Đà Lạt.",
        "ingredients": [("Pork", 120.0), ("Eggplant", 100.0), ("Bell Pepper", 50.0), ("Garlic", 8.0)],
    },
    {
        "code": "DISH_LAMB_SWEET_POTATO",
        "name_vi": "Thịt cừu nướng khoai lang & măng tây",
        "category": "Món mặn cao cấp",
        "description": "Bữa ăn giàu đạm và tinh bột chậm từ khoai lang.",
        "ingredients": [("Lamb", 130.0), ("Sweet Potato", 130.0), ("Asparagus", 60.0)],
    },
    {
        "code": "DISH_TROPICAL_FRUIT",
        "name_vi": "Tráng miệng trái cây tươi (Dưa hấu, Xoài, Thanh long)",
        "category": "Tráng miệng",
        "description": "Đĩa trái cây tươi bổ sung vitamin tự nhiên sau bữa.",
        "ingredients": [("Watermelon", 120.0), ("Mango", 80.0), ("Dragon Fruit", 80.0)],
    },
    {
        "code": "DISH_AVOCADO_BANANA_CASHEW",
        "name_vi": "Sinh tố bơ chuối & hạt điều",
        "category": "Tráng miệng / Bữa phụ",
        "description": "Bữa phụ giàu chất béo tốt và năng lượng.",
        "ingredients": [("Avocado", 80.0), ("Banana", 90.0), ("Cashew Nut", 20.0)],
    },
]

SEED_USERS: list[tuple[str, str, str, str]] = [
    ("admin", "admin123", "Đặng Nguyễn Hữu Huy", ROLE_ADMIN),
    ("chef", "chef123", "Phạm Hữu Tuân", ROLE_CHEF),
    ("khiem", "receiver123", "Nguyễn Chánh Khiêm", ROLE_RECEIVER),
    ("receiver", "receiver123", "Nguyễn Chánh Khiêm", ROLE_RECEIVER),
    ("hung", "receiver123", "Phạm Ngọc Hưng", ROLE_RECEIVER),
]


def _seed_demo_procurement_orders(conn: Any) -> None:
    """Seed 3 phiếu yêu cầu nguyên liệu mẫu (PENDING) chuẩn bị demo nếu chưa có."""
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    today_dt = datetime.now()
    food_rows = conn.execute("SELECT * FROM foods_nutrition").fetchall()
    food_map = {r["class_name"]: dict(r) for r in food_rows}

    demo_specs = [
        {
            "order_code": "PO-DEMO-EGG-01",
            "title": "[DEMO TRƯỜNG] Bữa sáng Trứng ốp la & Trứng luộc",
            "meal_date": today_dt.strftime("%Y-%m-%d"),
            "meal_shift": "Ca Sáng",
            "servings": 1,
            "target_kcal_per_serving": 150.0,
            "note": "Phiếu demo trực tiếp 1 quả trứng gà thật (~50g) tại trạm cân Raspberry Pi 4.",
            "dish_name": "Trứng gà ốp la & Trứng luộc (Demo 1 suất)",
            "dish_category": "Bữa sáng Demo",
            "created_at": now_dt.isoformat().replace("+00:00", "Z"),
            "ingredients": [("Egg", 50.0)],
        },
        {
            "order_code": "PO-DEMO-MON-02",
            "title": "Thực đơn Trưa Thứ Hai — Cơm gà kho & Canh rau củ",
            "meal_date": (today_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            "meal_shift": "Ca Trưa",
            "servings": 100,
            "target_kcal_per_serving": 650.0,
            "note": "Thực đơn mẫu bếp ăn tập thể 100 suất: Thịt gà kho trứng cùng canh khoai tây cà rốt cà chua.",
            "dish_name": "Cơm gà kho trứng & Canh rau củ thập cẩm",
            "dish_category": "Thực đơn Ca Trưa",
            "created_at": (now_dt - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
            "ingredients": [
                ("Chicken", 15000.0),
                ("Potato", 10000.0),
                ("Tomato", 6000.0),
                ("Carrot", 6000.0),
                ("Egg", 5000.0),
            ],
        },
        {
            "order_code": "PO-DEMO-TUE-03",
            "title": "Thực đơn Chiều Thứ Ba — Cá sốt cà & Tráng miệng",
            "meal_date": (today_dt + timedelta(days=2)).strftime("%Y-%m-%d"),
            "meal_shift": "Ca Chiều",
            "servings": 120,
            "target_kcal_per_serving": 600.0,
            "note": "Thực đơn mẫu bếp ăn tập thể 120 suất: Cá sốt cà chua, dưa chuột và chuối tráng miệng.",
            "dish_name": "Cá sốt cà chua, Dưa chuột & Chuối tráng miệng",
            "dish_category": "Thực đơn Ca Chiều",
            "created_at": (now_dt - timedelta(seconds=20)).isoformat().replace("+00:00", "Z"),
            "ingredients": [
                ("Fish", 18000.0),
                ("Banana", 10800.0),
                ("Cucumber", 9600.0),
                ("Tomato", 7200.0),
            ],
        },
    ]

    for spec in demo_specs:
        exists = conn.execute(
            "SELECT id FROM procurement_orders WHERE order_code = ?",
            (spec["order_code"],),
        ).fetchone()
        if exists:
            continue

        order_id = f"ord_{uuid.uuid4().hex[:10]}"
        total_kcal = 0.0
        total_protein = 0.0
        total_fat = 0.0
        total_carb = 0.0
        est_total_cost = 0

        item_rows: list[tuple[Any, ...]] = []
        tolerance = 5.0
        for cls_name, req_g in spec["ingredients"]:
            fn = food_map.get(cls_name)
            if not fn:
                continue
            edible_ratio = float(fn["edible_portion_percent"]) / 100.0
            factor = (req_g / 100.0) * edible_ratio
            total_kcal += float(fn["energy_kcal"]) * factor
            total_protein += float(fn["protein_g"]) * factor
            total_fat += float(fn["fat_g"]) * factor
            total_carb += float(fn["carbohydrate_g"]) * factor

            unit_p = int(fn["unit_price_vnd_per_kg"])
            est_cost = int(round((req_g / 1000.0) * unit_p))
            est_total_cost += est_cost
            min_acc = round(req_g * (1.0 - tolerance / 100.0), 1)
            item_rows.append((
                f"poi_{uuid.uuid4().hex[:10]}",
                order_id,
                fn["class_name"],
                fn["vietnamese_name"],
                fn["food_group"],
                req_g,
                tolerance,
                min_acc,
                unit_p,
                est_cost,
            ))

        dishes_json = json.dumps(
            [
                {
                    "id": 0,
                    "name_vi": spec["dish_name"],
                    "category": spec["dish_category"],
                    "kcal_per_serving": round(total_kcal / spec["servings"], 1),
                }
            ],
            ensure_ascii=False,
        )

        conn.execute(
            """
            INSERT INTO procurement_orders (
                id, order_code, title, meal_date, meal_shift, servings, dishes_json,
                total_kcal, total_protein_g, total_fat_g, total_carb_g,
                target_kcal_per_serving, estimated_total_cost_vnd,
                status, created_by, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 'chef', ?, ?)
            """,
            (
                order_id,
                spec["order_code"],
                spec["title"],
                spec["meal_date"],
                spec["meal_shift"],
                spec["servings"],
                dishes_json,
                round(total_kcal, 1),
                round(total_protein, 1),
                round(total_fat, 1),
                round(total_carb, 1),
                float(spec["target_kcal_per_serving"]),
                est_total_cost,
                spec["created_at"],
                spec["note"],
            ),
        )
        for row_vals in item_rows:
            conn.execute(
                """
                INSERT INTO procurement_items (
                    id, order_id, class_name, food_name_vi, food_group,
                    required_gram, tolerance_percent, min_acceptable_gram,
                    unit_price_per_kg, estimated_cost_vnd, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                row_vals,
            )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_migrations(conn: Any) -> None:
    """Bổ sung cột mới vào bảng cũ nếu database đã tồn tại từ phiên bản trước."""
    migrations = {
        "foods_nutrition": [("unit_price_vnd_per_kg", "INTEGER NOT NULL DEFAULT 40000")],
        "procurement_orders": [
            ("target_kcal_per_serving", "REAL NOT NULL DEFAULT 650.0"),
            ("estimated_total_cost_vnd", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "procurement_items": [
            ("unit_price_per_kg", "INTEGER NOT NULL DEFAULT 40000"),
            ("estimated_cost_vnd", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "intake_logs": [
            ("order_id", "TEXT DEFAULT ''"),
            ("order_item_id", "TEXT DEFAULT ''"),
            ("unit_price_per_kg", "INTEGER NOT NULL DEFAULT 0"),
            ("total_price_vnd", "INTEGER NOT NULL DEFAULT 0"),
        ],
    }
    for tbl, col_defs in migrations.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
        for col_name, col_sql in col_defs:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_sql}")


def init_database() -> None:
    """Khởi tạo toàn bộ bảng SQLite, seed 64 thực phẩm (kèm đơn giá), 3 tài khoản mẫu và 14 món ăn."""
    now = utc_now_iso()
    with get_db_conn() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_migrations(conn)

        # 1. Seed 64 loại thực phẩm chuẩn YOLO26n
        for profile in NUTRITION_TABLE_64.values():
            conn.execute(
                """
                INSERT OR IGNORE INTO foods_nutrition (
                    code, class_name, vietnamese_name, food_group,
                    edible_portion_percent, energy_kcal, protein_g, fat_g,
                    carbohydrate_g, fiber_g, calcium_mg, iron_mg, vitamin_c_mg,
                    unit_price_vnd_per_kg, source, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    profile.code,
                    profile.class_name,
                    profile.vietnamese_name,
                    profile.food_group,
                    profile.edible_portion_percent,
                    profile.energy_kcal,
                    profile.protein_g,
                    profile.fat_g,
                    profile.carbohydrate_g,
                    profile.fiber_g,
                    profile.calcium_mg,
                    profile.iron_mg,
                    profile.vitamin_c_mg,
                    profile.unit_price_vnd_per_kg,
                    profile.source,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE foods_nutrition
                SET unit_price_vnd_per_kg = ?
                WHERE class_name = ? AND unit_price_vnd_per_kg = 40000
                """,
                (profile.unit_price_vnd_per_kg, profile.class_name),
            )

        # 2. Seed tài khoản thành viên RBAC (tạo mới hoặc cập nhật họ tên/vai trò nếu đã tồn tại)
        for uname, raw_pw, fname, role in SEED_USERS:
            existing = conn.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    (uname, hash_password(raw_pw), fname, role, now),
                )
            else:
                conn.execute(
                    "UPDATE users SET full_name = ?, role = ?, is_active = 1 WHERE username = ?",
                    (fname, role, uname),
                )

        # 3. Seed 14 món ăn chuẩn (chỉ thêm nếu chưa có)
        for dish in SEED_DISHES:
            existing_dish = conn.execute("SELECT id FROM dishes WHERE code = ?", (dish["code"],)).fetchone()
            if existing_dish:
                continue
            cur = conn.execute(
                """
                INSERT INTO dishes (code, name_vi, category, description, is_active, created_by, updated_at)
                VALUES (?, ?, ?, ?, 1, 'system', ?)
                """,
                (dish["code"], dish["name_vi"], dish["category"], dish["description"], now),
            )
            dish_id = cur.lastrowid
            for cls_name, grams in dish["ingredients"]:
                conn.execute(
                    """
                    INSERT INTO dish_ingredients (dish_id, class_name, grams_per_serving)
                    VALUES (?, ?, ?)
                    """,
                    (dish_id, cls_name, grams),
                )

        # 4. Seed 3 phiếu chuẩn bị nguyên liệu mẫu cho Demo bảo vệ (PENDING)
        _seed_demo_procurement_orders(conn)

    logger.info("[DB] Đã khởi tạo SQLite Enterprise (Users, 64 Foods, 14 Dishes, Demo Orders, Logs).")


# ==============================================================================
# USER & RBAC CRUD
# ==============================================================================

def _row_to_user(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with get_db_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id ASC").fetchall()
    return [_row_to_user(r) for r in rows]


def create_user(username: str, password: str, full_name: str, role: str) -> dict[str, Any]:
    now = utc_now_iso()
    with get_db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (username.strip().lower(), hash_password(password), full_name.strip(), role.upper(), now),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_user(row)


def update_user(user_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    updates: dict[str, Any] = {}
    if "full_name" in fields and fields["full_name"] is not None:
        updates["full_name"] = str(fields["full_name"]).strip()
    if "role" in fields and fields["role"] is not None:
        updates["role"] = str(fields["role"]).upper()
    if "is_active" in fields and fields["is_active"] is not None:
        updates["is_active"] = 1 if fields["is_active"] else 0
    if "password" in fields and fields["password"]:
        updates["password_hash"] = hash_password(str(fields["password"]))

    with get_db_conn() as conn:
        if updates:
            assignments = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", list(updates.values()) + [user_id])
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def delete_user(user_id: int) -> bool:
    with get_db_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


# ==============================================================================
# FOODS NUTRITION (64 CLASSES)
# ==============================================================================

def _row_to_food(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "class_name": row["class_name"],
        "vietnamese_name": row["vietnamese_name"],
        "food_group": row["food_group"],
        "edible_portion_percent": row["edible_portion_percent"],
        "energy_kcal": row["energy_kcal"],
        "protein_g": row["protein_g"],
        "fat_g": row["fat_g"],
        "carbohydrate_g": row["carbohydrate_g"],
        "fiber_g": row["fiber_g"],
        "calcium_mg": row["calcium_mg"],
        "iron_mg": row["iron_mg"],
        "vitamin_c_mg": row["vitamin_c_mg"],
        "unit_price_vnd_per_kg": row["unit_price_vnd_per_kg"],
        "source": row["source"],
        "is_active": bool(row["is_active"]),
        "updated_at": row["updated_at"],
    }


def list_foods(search: str | None = None, food_group: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM foods_nutrition WHERE 1=1"
    params: list[Any] = []
    if search:
        sql += " AND (LOWER(class_name) LIKE ? OR LOWER(vietnamese_name) LIKE ? OR LOWER(code) LIKE ?)"
        q = f"%{search.strip().lower()}%"
        params.extend([q, q, q])
    if food_group:
        sql += " AND food_group = ?"
        params.append(food_group.strip())
    sql += " ORDER BY vietnamese_name ASC"

    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_food(r) for r in rows]


def get_food_by_label(label: str) -> dict[str, Any] | None:
    clean = normalize_label(label)
    if not clean or clean == "Unknown":
        return None
    with get_db_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM foods_nutrition
            WHERE LOWER(class_name) = LOWER(?)
               OR LOWER(code) = LOWER(?)
               OR LOWER(vietnamese_name) = LOWER(?)
            LIMIT 1
            """,
            (clean, clean.replace(" ", "_"), clean),
        ).fetchone()
    return _row_to_food(row) if row else None


def update_food_nutrition(food_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "vietnamese_name", "food_group", "edible_portion_percent",
        "energy_kcal", "protein_g", "fat_g", "carbohydrate_g",
        "fiber_g", "calcium_mg", "iron_mg", "vitamin_c_mg", "unit_price_vnd_per_kg", "is_active",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    with get_db_conn() as conn:
        if updates:
            if "is_active" in updates:
                updates["is_active"] = 1 if updates["is_active"] else 0
            updates["updated_at"] = utc_now_iso()
            assignments = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE foods_nutrition SET {assignments} WHERE id = ?", list(updates.values()) + [food_id])
        row = conn.execute("SELECT * FROM foods_nutrition WHERE id = ?", (food_id,)).fetchone()
    return _row_to_food(row) if row else None


# ==============================================================================
# DISHES & RECIPES (STRICTLY 64 DATASET INGREDIENTS)
# ==============================================================================

def _hydrate_dish(conn: Any, dish_row: Any) -> dict[str, Any]:
    ing_rows = conn.execute(
        """
        SELECT di.id, di.class_name, di.grams_per_serving,
               fn.vietnamese_name, fn.food_group, fn.edible_portion_percent,
               fn.energy_kcal, fn.protein_g, fn.fat_g, fn.carbohydrate_g, fn.fiber_g
        FROM dish_ingredients di
        JOIN foods_nutrition fn ON fn.class_name = di.class_name
        WHERE di.dish_id = ?
        ORDER BY di.id ASC
        """,
        (dish_row["id"],),
    ).fetchall()

    total_kcal = 0.0
    total_protein = 0.0
    total_fat = 0.0
    total_carb = 0.0
    total_grams = 0.0
    ingredients: list[dict[str, Any]] = []

    for r in ing_rows:
        g = float(r["grams_per_serving"])
        edible_g = g * (float(r["edible_portion_percent"]) / 100.0)
        factor = edible_g / 100.0
        kcal = round(float(r["energy_kcal"]) * factor, 1)
        prot = round(float(r["protein_g"]) * factor, 2)
        fat = round(float(r["fat_g"]) * factor, 2)
        carb = round(float(r["carbohydrate_g"]) * factor, 2)

        total_grams += g
        total_kcal += kcal
        total_protein += prot
        total_fat += fat
        total_carb += carb

        ingredients.append({
            "id": r["id"],
            "class_name": r["class_name"],
            "vietnamese_name": r["vietnamese_name"],
            "food_group": r["food_group"],
            "grams_per_serving": g,
            "edible_portion_percent": r["edible_portion_percent"],
            "kcal_per_serving": kcal,
            "protein_per_serving": prot,
            "fat_per_serving": fat,
            "carb_per_serving": carb,
        })

    return {
        "id": dish_row["id"],
        "code": dish_row["code"],
        "name_vi": dish_row["name_vi"],
        "category": dish_row["category"],
        "description": dish_row["description"],
        "is_active": bool(dish_row["is_active"]),
        "created_by": dish_row["created_by"],
        "updated_at": dish_row["updated_at"],
        "ingredients": ingredients,
        "per_serving": {
            "total_grams": round(total_grams, 1),
            "energy_kcal": round(total_kcal, 1),
            "protein_g": round(total_protein, 1),
            "fat_g": round(total_fat, 1),
            "carbohydrate_g": round(total_carb, 1),
        },
    }


def list_dishes(search: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM dishes WHERE is_active = 1"
    params: list[Any] = []
    if search:
        sql += " AND (LOWER(name_vi) LIKE ? OR LOWER(code) LIKE ?)"
        q = f"%{search.strip().lower()}%"
        params.extend([q, q])
    if category:
        sql += " AND category = ?"
        params.append(category.strip())
    sql += " ORDER BY id DESC"

    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_hydrate_dish(conn, r) for r in rows]


def get_dish_by_id(dish_id: int) -> dict[str, Any] | None:
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)).fetchone()
        return _hydrate_dish(conn, row) if row else None


def create_dish(
    name_vi: str,
    category: str,
    description: str,
    ingredients: list[dict[str, Any]],
    created_by: str = "chef",
) -> dict[str, Any]:
    """Tạo mới món ăn từ danh sách 64 nguyên liệu chuẩn."""
    if not ingredients:
        raise ValueError("Món ăn phải có ít nhất 1 nguyên liệu từ danh sách 64 loại chuẩn.")

    now = utc_now_iso()
    code = f"DISH_{uuid.uuid4().hex[:8].upper()}"
    with get_db_conn() as conn:
        # Kiểm tra 100% nguyên liệu thuộc bảng 64 lớp
        for ing in ingredients:
            cls_name = str(ing.get("class_name", "")).strip()
            exists = conn.execute(
                "SELECT class_name FROM foods_nutrition WHERE LOWER(class_name) = LOWER(?)",
                (cls_name,),
            ).fetchone()
            if not exists:
                raise ValueError(f"Nguyên liệu '{cls_name}' không nằm trong 64 lớp YOLO26n chuẩn.")

        cur = conn.execute(
            """
            INSERT INTO dishes (code, name_vi, category, description, is_active, created_by, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (code, name_vi.strip(), category.strip(), description.strip(), created_by, now),
        )
        dish_id = cur.lastrowid
        for ing in ingredients:
            cls_name = str(ing["class_name"]).strip()
            row_fn = conn.execute(
                "SELECT class_name FROM foods_nutrition WHERE LOWER(class_name) = LOWER(?)",
                (cls_name,),
            ).fetchone()
            grams = float(ing["grams_per_serving"])
            if grams <= 0:
                raise ValueError("Định lượng mỗi suất phải lớn hơn 0g.")
            conn.execute(
                "INSERT INTO dish_ingredients (dish_id, class_name, grams_per_serving) VALUES (?, ?, ?)",
                (dish_id, row_fn["class_name"], grams),
            )
        row = conn.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)).fetchone()
        return _hydrate_dish(conn, row)


def delete_dish(dish_id: int) -> bool:
    with get_db_conn() as conn:
        cur = conn.execute("UPDATE dishes SET is_active = 0 WHERE id = ?", (dish_id,))
        return cur.rowcount > 0


# ==============================================================================
# PROCUREMENT ORDERS & CHECKLIST (PHIẾU YÊU CẦU NGUYÊN LIỆU)
# ==============================================================================

def _hydrate_order(conn: Any, order_row: Any) -> dict[str, Any]:
    items = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM procurement_items WHERE order_id = ? ORDER BY required_gram DESC",
            (order_row["id"],),
        ).fetchall()
    ]
    log_rows = conn.execute(
        "SELECT id, weight_gram, energy_kcal, total_price_vnd FROM intake_logs WHERE order_id = ?",
        (order_row["id"],),
    ).fetchall()
    log_map = {r["id"]: dict(r) for r in log_rows}

    total_items = len(items)
    completed_items = sum(1 for it in items if it["status"] == "COMPLETED")
    actual_total_gram = 0.0
    actual_total_cost_vnd = 0
    actual_total_kcal = 0.0

    for it in items:
        if it["status"] != "COMPLETED":
            continue
        gram = float(it.get("actual_gram") or 0.0)
        actual_total_gram += gram
        log_doc = log_map.get(it.get("log_id") or "")
        if log_doc:
            actual_total_cost_vnd += int(log_doc.get("total_price_vnd") or 0)
            actual_total_kcal += float(log_doc.get("energy_kcal") or 0.0)
        else:
            actual_total_cost_vnd += int(round((gram / 1000.0) * int(it.get("unit_price_per_kg") or 40000)))

    return {
        "id": order_row["id"],
        "order_code": order_row["order_code"],
        "title": order_row["title"],
        "meal_date": order_row["meal_date"],
        "meal_shift": order_row["meal_shift"],
        "servings": order_row["servings"],
        "dishes": json.loads(order_row["dishes_json"]),
        "total_kcal": order_row["total_kcal"],
        "total_protein_g": order_row["total_protein_g"],
        "total_fat_g": order_row["total_fat_g"],
        "total_carb_g": order_row["total_carb_g"],
        "target_kcal_per_serving": order_row["target_kcal_per_serving"],
        "estimated_total_cost_vnd": order_row["estimated_total_cost_vnd"],
        "status": order_row["status"],
        "created_by": order_row["created_by"],
        "created_at": order_row["created_at"],
        "completed_at": order_row["completed_at"],
        "note": order_row["note"],
        "progress": {
            "completed": completed_items,
            "total": total_items,
            "percent": round((completed_items / total_items) * 100.0, 1) if total_items else 0.0,
        },
        "actual_summary": {
            "total_gram": round(actual_total_gram, 1),
            "total_cost_vnd": int(actual_total_cost_vnd),
            "total_kcal": round(actual_total_kcal, 1),
        },
        "items": items,
    }


def create_procurement_order(
    title: str,
    meal_date: str,
    meal_shift: str,
    servings: int,
    dish_ids: list[int],
    created_by: str,
    note: str = "",
    tolerance_percent: float = 5.0,
    target_kcal_per_serving: float = 650.0,
) -> dict[str, Any]:
    """Lập kế hoạch bữa ăn -> Tính tổng Calo/Macro/Chi phí dự kiến -> Sinh Phiếu Yêu Cầu Nguyên Liệu."""
    if servings <= 0:
        raise ValueError("Số lượng suất ăn phải lớn hơn 0.")
    if not dish_ids:
        raise ValueError("Vui lòng chọn ít nhất 1 món ăn cho thực đơn.")

    order_id = f"ord_{uuid.uuid4().hex[:10]}"
    order_code = f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    now = utc_now_iso()

    with get_db_conn() as conn:
        aggregated_ingredients: dict[str, dict[str, Any]] = {}
        selected_dishes: list[dict[str, Any]] = []
        total_kcal = 0.0
        total_protein = 0.0
        total_fat = 0.0
        total_carb = 0.0

        # Lấy đơn giá tham khảo của 64 nguyên liệu
        price_rows = conn.execute("SELECT class_name, unit_price_vnd_per_kg FROM foods_nutrition").fetchall()
        price_map = {r["class_name"]: int(r["unit_price_vnd_per_kg"]) for r in price_rows}

        for did in dish_ids:
            dish_row = conn.execute("SELECT * FROM dishes WHERE id = ? AND is_active = 1", (did,)).fetchone()
            if not dish_row:
                raise ValueError(f"Không tìm thấy món ăn ID={did}.")
            dish_data = _hydrate_dish(conn, dish_row)
            selected_dishes.append({
                "id": dish_data["id"],
                "name_vi": dish_data["name_vi"],
                "category": dish_data["category"],
                "kcal_per_serving": dish_data["per_serving"]["energy_kcal"],
            })
            total_kcal += dish_data["per_serving"]["energy_kcal"] * servings
            total_protein += dish_data["per_serving"]["protein_g"] * servings
            total_fat += dish_data["per_serving"]["fat_g"] * servings
            total_carb += dish_data["per_serving"]["carbohydrate_g"] * servings

            for ing in dish_data["ingredients"]:
                cls_name = ing["class_name"]
                req_g = round(float(ing["grams_per_serving"]) * servings, 1)
                unit_price = price_map.get(cls_name, 40000)
                if cls_name not in aggregated_ingredients:
                    aggregated_ingredients[cls_name] = {
                        "class_name": cls_name,
                        "food_name_vi": ing["vietnamese_name"],
                        "food_group": ing["food_group"],
                        "required_gram": req_g,
                        "unit_price_per_kg": unit_price,
                    }
                else:
                    aggregated_ingredients[cls_name]["required_gram"] = round(
                        aggregated_ingredients[cls_name]["required_gram"] + req_g, 1
                    )

        est_total_cost = sum(
            int(round((it["required_gram"] / 1000.0) * it["unit_price_per_kg"]))
            for it in aggregated_ingredients.values()
        )

        conn.execute(
            """
            INSERT INTO procurement_orders (
                id, order_code, title, meal_date, meal_shift, servings, dishes_json,
                total_kcal, total_protein_g, total_fat_g, total_carb_g,
                target_kcal_per_serving, estimated_total_cost_vnd,
                status, created_by, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)
            """,
            (
                order_id, order_code, title.strip(), meal_date, meal_shift, servings,
                json.dumps(selected_dishes, ensure_ascii=False),
                round(total_kcal, 1), round(total_protein, 1), round(total_fat, 1), round(total_carb, 1),
                float(target_kcal_per_serving), est_total_cost,
                created_by, now, note.strip(),
            ),
        )

        for item in aggregated_ingredients.values():
            req = item["required_gram"]
            min_acc = round(req * (1.0 - tolerance_percent / 100.0), 1)
            unit_p = int(item["unit_price_per_kg"])
            est_cost = int(round((req / 1000.0) * unit_p))
            item_id = f"poi_{uuid.uuid4().hex[:10]}"
            conn.execute(
                """
                INSERT INTO procurement_items (
                    id, order_id, class_name, food_name_vi, food_group,
                    required_gram, tolerance_percent, min_acceptable_gram,
                    unit_price_per_kg, estimated_cost_vnd, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    item_id, order_id, item["class_name"], item["food_name_vi"],
                    item["food_group"], req, tolerance_percent, min_acc, unit_p, est_cost,
                ),
            )

        order_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        return _hydrate_order(conn, order_row)


def list_procurement_orders(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM procurement_orders WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status.upper())
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_hydrate_order(conn, r) for r in rows]


def get_procurement_order(order_id: str) -> dict[str, Any] | None:
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        return _hydrate_order(conn, row) if row else None


def mark_procurement_item_completed(
    order_id: str,
    item_id: str,
    actual_gram: float,
    quality_status: str,
    confidence: float,
    checked_by: str,
    log_id: str,
    image_url: str | None = None,
    accumulate: bool = False,
) -> dict[str, Any]:
    """Đánh dấu TÍCH XANH nguyên liệu trong phiếu: chỉ ghi đè khi chưa COMPLETED, chỉ cộng dồn khi accumulate=True và đã COMPLETED."""
    now = utc_now_iso()
    with get_db_conn() as conn:
        item_row = conn.execute(
            "SELECT * FROM procurement_items WHERE id = ? AND order_id = ?",
            (item_id, order_id),
        ).fetchone()
        if not item_row:
            raise ValueError("Không tìm thấy dòng nguyên liệu trong phiếu yêu cầu.")

        grams_rounded = round(float(actual_gram), 1)
        is_checked = item_row["status"] == "COMPLETED"
        if accumulate and is_checked:
            new_actual_gram = round(float(item_row["actual_gram"] or 0.0) + grams_rounded, 1)
        else:
            # Nếu nguyên liệu chưa hoàn thành (is_checked == False), lấy đúng trọng lượng hiện tại, không cộng dồn nhầm
            new_actual_gram = grams_rounded

        conn.execute(
            """
            UPDATE procurement_items
            SET actual_gram = ?, quality_status = ?, confidence = ?,
                status = 'COMPLETED', checked_by = ?, checked_at = ?,
                log_id = ?, image_url = ?
            WHERE id = ?
            """,
            (
                new_actual_gram, quality_status, round(confidence, 3),
                checked_by, now, log_id, image_url or "", item_id,
            ),
        )

        # Kiểm tra nếu tất cả nguyên liệu trong phiếu đã COMPLETED -> chuyển đơn sang COMPLETED
        pending = conn.execute(
            "SELECT COUNT(*) AS cnt FROM procurement_items WHERE order_id = ? AND status != 'COMPLETED'",
            (order_id,),
        ).fetchone()["cnt"]

        if pending == 0:
            conn.execute(
                "UPDATE procurement_orders SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                (now, order_id),
            )
        else:
            conn.execute(
                "UPDATE procurement_orders SET status = 'IN_PROGRESS' WHERE id = ? AND status = 'PENDING'",
                (order_id,),
            )

        order_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        return _hydrate_order(conn, order_row)


def reset_procurement_order(order_id: str) -> dict[str, Any] | None:
    """Đặt lại toàn bộ trạng thái tích xanh của phiếu về PENDING để demo hoặc cân nhập lại."""
    with get_db_conn() as conn:
        order_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        if not order_row:
            return None

        conn.execute(
            """
            UPDATE procurement_items
            SET actual_gram = 0.0, quality_status = '', confidence = 0.0,
                status = 'PENDING', checked_by = '', checked_at = '',
                log_id = '', image_url = ''
            WHERE order_id = ?
            """,
            (order_id,),
        )
        conn.execute(
            "UPDATE procurement_orders SET status = 'PENDING', completed_at = NULL WHERE id = ?",
            (order_id,),
        )
        updated_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        return _hydrate_order(conn, updated_row)


def add_procurement_order_item(
    order_id: str,
    class_name: str,
    required_gram: float,
    tolerance_percent: float = 5.0,
    mark_completed: bool = False,
    actual_gram: float | None = None,
    quality_status: str = "FRESH",
    confidence: float = 0.0,
    checked_by: str = "",
    log_id: str = "",
    image_url: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Thêm nguyên liệu (phát sinh tại trạm hoặc bổ sung thủ công từ 64 loại) vào phiếu hiện tại."""
    req_g = round(float(required_gram), 1)
    if req_g <= 0:
        raise ValueError("Khối lượng nguyên liệu bổ sung phải lớn hơn 0g.")

    now = utc_now_iso()
    with get_db_conn() as conn:
        order_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        if not order_row:
            raise ValueError("Không tìm thấy Phiếu yêu cầu nguyên liệu.")

        fn = conn.execute(
            "SELECT * FROM foods_nutrition WHERE LOWER(class_name) = LOWER(?)",
            (class_name.strip(),),
        ).fetchone()
        if not fn:
            raise ValueError(f"Nguyên liệu '{class_name}' không thuộc 64 lớp thực phẩm chuẩn.")

        edible_ratio = float(fn["edible_portion_percent"]) / 100.0
        factor = (req_g / 100.0) * edible_ratio
        add_kcal = float(fn["energy_kcal"]) * factor
        add_protein = float(fn["protein_g"]) * factor
        add_fat = float(fn["fat_g"]) * factor
        add_carb = float(fn["carbohydrate_g"]) * factor
        unit_p = int(fn["unit_price_vnd_per_kg"])
        est_cost = int(round((req_g / 1000.0) * unit_p))
        min_acc = round(req_g * (1.0 - float(tolerance_percent) / 100.0), 1)

        existing_pending = None
        if not mark_completed:
            existing_pending = conn.execute(
                """
                SELECT * FROM procurement_items
                WHERE order_id = ? AND LOWER(class_name) = LOWER(?) AND status = 'PENDING'
                """,
                (order_id, fn["class_name"]),
            ).fetchone()

        if existing_pending:
            new_req = round(float(existing_pending["required_gram"]) + req_g, 1)
            new_min = round(new_req * (1.0 - float(existing_pending["tolerance_percent"]) / 100.0), 1)
            new_cost = int(round((new_req / 1000.0) * unit_p))
            item_id = existing_pending["id"]
            conn.execute(
                """
                UPDATE procurement_items
                SET required_gram = ?, min_acceptable_gram = ?, estimated_cost_vnd = ?
                WHERE id = ?
                """,
                (new_req, new_min, new_cost, item_id),
            )
        else:
            item_id = f"poi_{uuid.uuid4().hex[:10]}"
            act_g = round(float(actual_gram if actual_gram is not None else req_g), 1) if mark_completed else 0.0
            conn.execute(
                """
                INSERT INTO procurement_items (
                    id, order_id, class_name, food_name_vi, food_group,
                    required_gram, tolerance_percent, min_acceptable_gram,
                    unit_price_per_kg, estimated_cost_vnd,
                    actual_gram, quality_status, confidence, status,
                    checked_by, checked_at, log_id, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    order_id,
                    fn["class_name"],
                    fn["vietnamese_name"],
                    fn["food_group"],
                    req_g,
                    float(tolerance_percent),
                    min_acc,
                    unit_p,
                    est_cost,
                    act_g,
                    quality_status if mark_completed else "",
                    round(float(confidence), 3) if mark_completed else 0.0,
                    "COMPLETED" if mark_completed else "PENDING",
                    checked_by if mark_completed else "",
                    now if mark_completed else "",
                    log_id if mark_completed else "",
                    (image_url or "") if mark_completed else "",
                ),
            )

        # Cập nhật tổng dinh dưỡng & chi phí dự kiến của phiếu
        conn.execute(
            """
            UPDATE procurement_orders
            SET total_kcal = ROUND(total_kcal + ?, 1),
                total_protein_g = ROUND(total_protein_g + ?, 1),
                total_fat_g = ROUND(total_fat_g + ?, 1),
                total_carb_g = ROUND(total_carb_g + ?, 1),
                estimated_total_cost_vnd = estimated_total_cost_vnd + ?
            WHERE id = ?
            """,
            (add_kcal, add_protein, add_fat, add_carb, est_cost, order_id),
        )

        # Cập nhật lại trạng thái đơn hàng dựa trên tiến độ các dòng
        pending_cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM procurement_items WHERE order_id = ? AND status != 'COMPLETED'",
            (order_id,),
        ).fetchone()["cnt"]
        completed_cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM procurement_items WHERE order_id = ? AND status = 'COMPLETED'",
            (order_id,),
        ).fetchone()["cnt"]

        if pending_cnt == 0 and completed_cnt > 0:
            conn.execute(
                "UPDATE procurement_orders SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                (now, order_id),
            )
        elif completed_cnt > 0:
            conn.execute(
                "UPDATE procurement_orders SET status = 'IN_PROGRESS', completed_at = NULL WHERE id = ?",
                (order_id,),
            )
        else:
            conn.execute(
                "UPDATE procurement_orders SET status = 'PENDING', completed_at = NULL WHERE id = ?",
                (order_id,),
            )

        updated_order_row = conn.execute("SELECT * FROM procurement_orders WHERE id = ?", (order_id,)).fetchone()
        item_row = conn.execute("SELECT * FROM procurement_items WHERE id = ?", (item_id,)).fetchone()
        return _hydrate_order(conn, updated_order_row), dict(item_row)


# ==============================================================================
# INTAKE LOGS & DAILY ANALYTICS
# ==============================================================================

def insert_intake_log(doc: dict[str, Any]) -> dict[str, Any]:
    local_date = doc.get("local_date") or local_today_str()
    with get_db_conn() as conn:
        conn.execute(
            """
            INSERT INTO intake_logs (
                id, batch_code, timestamp, local_date, station_id,
                class_name, food_name_vi, food_group,
                weight_gram, edible_gram, quality_status, confidence,
                inference_time_ms, strategy,
                energy_kcal, protein_g, fat_g, carbohydrate_g, fiber_g,
                calcium_mg, iron_mg, vitamin_c_mg,
                image_url, note, confirmed_by, order_id, order_item_id,
                unit_price_per_kg, total_price_vnd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc["id"], doc["batch_code"], doc["timestamp"], local_date, doc["station_id"],
                doc["class_name"], doc["food_name_vi"], doc["food_group"],
                doc["weight_gram"], doc["edible_gram"], doc["quality_status"], doc["confidence"],
                doc["inference_time_ms"], doc["strategy"],
                doc["energy_kcal"], doc["protein_g"], doc["fat_g"], doc["carbohydrate_g"], doc["fiber_g"],
                doc["calcium_mg"], doc["iron_mg"], doc["vitamin_c_mg"],
                doc.get("image_url"), doc.get("note", ""), doc.get("confirmed_by", "Trạm cân AI"),
                doc.get("order_id", ""), doc.get("order_item_id", ""),
                int(doc.get("unit_price_per_kg", 0)), int(doc.get("total_price_vnd", 0)),
            ),
        )

        is_accepted = doc["quality_status"] != "REJECTED"
        row = conn.execute("SELECT * FROM daily_nutrition_analytics WHERE date = ?", (local_date,)).fetchone()

        w_kg = round(doc["weight_gram"] / 1000.0, 4)
        acc_kg = w_kg if is_accepted else 0.0
        add_kcal = doc["energy_kcal"] if is_accepted else 0.0
        add_p = doc["protein_g"] if is_accepted else 0.0
        add_f = doc["fat_g"] if is_accepted else 0.0
        add_c = doc["carbohydrate_g"] if is_accepted else 0.0
        add_fib = doc["fiber_g"] if is_accepted else 0.0

        fresh_inc = 1 if doc["quality_status"] == "FRESH" else 0
        warn_inc = 1 if doc["quality_status"] == "WARNING" else 0
        rej_inc = 1 if doc["quality_status"] == "REJECTED" else 0

        if row is None:
            conn.execute(
                """
                INSERT INTO daily_nutrition_analytics (
                    date, total_batches, fresh_count, warning_count, rejected_count,
                    total_weight_kg, accepted_weight_kg, total_kcal,
                    total_protein_g, total_fat_g, total_carb_g, total_fiber_g
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    local_date, fresh_inc, warn_inc, rej_inc,
                    w_kg, acc_kg, round(add_kcal, 1),
                    round(add_p, 1), round(add_f, 1), round(add_c, 1), round(add_fib, 1),
                ),
            )
        else:
            conn.execute(
                """
                UPDATE daily_nutrition_analytics
                SET total_batches = total_batches + 1,
                    fresh_count = fresh_count + ?,
                    warning_count = warning_count + ?,
                    rejected_count = rejected_count + ?,
                    total_weight_kg = ROUND(total_weight_kg + ?, 3),
                    accepted_weight_kg = ROUND(accepted_weight_kg + ?, 3),
                    total_kcal = ROUND(total_kcal + ?, 1),
                    total_protein_g = ROUND(total_protein_g + ?, 1),
                    total_fat_g = ROUND(total_fat_g + ?, 1),
                    total_carb_g = ROUND(total_carb_g + ?, 1),
                    total_fiber_g = ROUND(total_fiber_g + ?, 1)
                WHERE date = ?
                """,
                (
                    fresh_inc, warn_inc, rej_inc,
                    w_kg, acc_kg, add_kcal, add_p, add_f, add_c, add_fib,
                    local_date,
                ),
            )
    return doc


def list_intake_logs(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    quality_status: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM intake_logs WHERE 1=1"
    params: list[Any] = []
    if date_from:
        sql += " AND local_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND local_date <= ?"
        params.append(date_to)
    if quality_status:
        sql += " AND quality_status = ?"
        params.append(quality_status.upper())
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    with get_db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def delete_intake_log(log_id: str) -> bool:
    with get_db_conn() as conn:
        cur = conn.execute("DELETE FROM intake_logs WHERE id = ?", (log_id,))
        return cur.rowcount > 0


def get_daily_analytics(days: int = 14) -> list[dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(days=max(1, days - 1))).strftime("%Y-%m-%d")
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_nutrition_analytics WHERE date >= ? ORDER BY date ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary_kpis(days: int = 7) -> dict[str, Any]:
    today = local_today_str()
    week_start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    with get_db_conn() as conn:
        today_row = conn.execute("SELECT * FROM daily_nutrition_analytics WHERE date = ?", (today,)).fetchone()
        week_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_batches), 0) AS total_batches,
                COALESCE(SUM(fresh_count), 0) AS fresh_count,
                COALESCE(SUM(warning_count), 0) AS warning_count,
                COALESCE(SUM(rejected_count), 0) AS rejected_count,
                COALESCE(SUM(total_weight_kg), 0.0) AS total_weight_kg,
                COALESCE(SUM(accepted_weight_kg), 0.0) AS accepted_weight_kg,
                COALESCE(SUM(total_kcal), 0.0) AS total_kcal,
                COALESCE(SUM(total_protein_g), 0.0) AS total_protein_g,
                COALESCE(SUM(total_fat_g), 0.0) AS total_fat_g,
                COALESCE(SUM(total_carb_g), 0.0) AS total_carb_g
            FROM daily_nutrition_analytics
            WHERE date >= ?
            """,
            (week_start,),
        ).fetchone()
        orders_stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                SUM(CASE WHEN status IN ('PENDING', 'IN_PROGRESS') THEN 1 ELSE 0 END) AS active_orders,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_orders
            FROM procurement_orders
            """
        ).fetchone()

    empty_today = {
        "date": today, "total_batches": 0, "fresh_count": 0, "warning_count": 0,
        "rejected_count": 0, "total_weight_kg": 0.0, "accepted_weight_kg": 0.0,
        "total_kcal": 0.0, "total_protein_g": 0.0, "total_fat_g": 0.0,
        "total_carb_g": 0.0, "total_fiber_g": 0.0,
    }
    return {
        "today": dict(today_row) if today_row else empty_today,
        "period_days": days,
        "period_summary": dict(week_row) if week_row else empty_today,
        "orders": {
            "total_orders": orders_stats["total_orders"] or 0,
            "active_orders": orders_stats["active_orders"] or 0,
            "completed_orders": orders_stats["completed_orders"] or 0,
        },
    }
