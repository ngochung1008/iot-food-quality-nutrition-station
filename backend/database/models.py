"""Định nghĩa schema SQLite hoàn chỉnh cho nền tảng SaaS Quản lý Bếp ăn Tập thể."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from backend.core.config import settings

_db_lock = threading.RLock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'CHEF', 'RECEIVER')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foods_nutrition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    class_name TEXT UNIQUE NOT NULL,
    vietnamese_name TEXT NOT NULL,
    food_group TEXT NOT NULL,
    edible_portion_percent REAL NOT NULL DEFAULT 100.0,
    energy_kcal REAL NOT NULL DEFAULT 0.0,
    protein_g REAL NOT NULL DEFAULT 0.0,
    fat_g REAL NOT NULL DEFAULT 0.0,
    carbohydrate_g REAL NOT NULL DEFAULT 0.0,
    fiber_g REAL NOT NULL DEFAULT 0.0,
    calcium_mg REAL NOT NULL DEFAULT 0.0,
    iron_mg REAL NOT NULL DEFAULT 0.0,
    vitamin_c_mg REAL NOT NULL DEFAULT 0.0,
    unit_price_vnd_per_kg INTEGER NOT NULL DEFAULT 40000,
    source TEXT NOT NULL DEFAULT 'VTN_FCT_2007',
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name_vi TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT DEFAULT 'system',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dish_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_id INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    grams_per_serving REAL NOT NULL,
    FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
    FOREIGN KEY(class_name) REFERENCES foods_nutrition(class_name)
);

CREATE TABLE IF NOT EXISTS procurement_orders (
    id TEXT PRIMARY KEY,
    order_code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    meal_date TEXT NOT NULL,
    meal_shift TEXT NOT NULL DEFAULT 'Bữa trưa',
    servings INTEGER NOT NULL DEFAULT 100,
    dishes_json TEXT NOT NULL,
    total_kcal REAL NOT NULL DEFAULT 0.0,
    total_protein_g REAL NOT NULL DEFAULT 0.0,
    total_fat_g REAL NOT NULL DEFAULT 0.0,
    total_carb_g REAL NOT NULL DEFAULT 0.0,
    target_kcal_per_serving REAL NOT NULL DEFAULT 650.0,
    estimated_total_cost_vnd INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS procurement_items (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    food_name_vi TEXT NOT NULL,
    food_group TEXT NOT NULL,
    required_gram REAL NOT NULL,
    tolerance_percent REAL NOT NULL DEFAULT 5.0,
    min_acceptable_gram REAL NOT NULL,
    unit_price_per_kg INTEGER NOT NULL DEFAULT 40000,
    estimated_cost_vnd INTEGER NOT NULL DEFAULT 0,
    actual_gram REAL NOT NULL DEFAULT 0.0,
    quality_status TEXT DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    checked_by TEXT DEFAULT '',
    checked_at TEXT DEFAULT '',
    log_id TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    FOREIGN KEY(order_id) REFERENCES procurement_orders(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_proc_items_order ON procurement_items(order_id);

CREATE TABLE IF NOT EXISTS intake_logs (
    id TEXT PRIMARY KEY,
    batch_code TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    local_date TEXT NOT NULL,
    station_id TEXT NOT NULL,
    class_name TEXT NOT NULL,
    food_name_vi TEXT NOT NULL,
    food_group TEXT NOT NULL,
    weight_gram REAL NOT NULL,
    edible_gram REAL NOT NULL,
    quality_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    inference_time_ms INTEGER NOT NULL DEFAULT 0,
    strategy TEXT NOT NULL DEFAULT 'ncnn',
    energy_kcal REAL NOT NULL DEFAULT 0.0,
    protein_g REAL NOT NULL DEFAULT 0.0,
    fat_g REAL NOT NULL DEFAULT 0.0,
    carbohydrate_g REAL NOT NULL DEFAULT 0.0,
    fiber_g REAL NOT NULL DEFAULT 0.0,
    calcium_mg REAL NOT NULL DEFAULT 0.0,
    iron_mg REAL NOT NULL DEFAULT 0.0,
    vitamin_c_mg REAL NOT NULL DEFAULT 0.0,
    image_url TEXT,
    note TEXT DEFAULT '',
    confirmed_by TEXT DEFAULT 'Trạm cân AI',
    order_id TEXT DEFAULT '',
    order_item_id TEXT DEFAULT '',
    unit_price_per_kg INTEGER NOT NULL DEFAULT 0,
    total_price_vnd INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_intake_logs_ts ON intake_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_intake_logs_date ON intake_logs(local_date DESC);

CREATE TABLE IF NOT EXISTS daily_nutrition_analytics (
    date TEXT PRIMARY KEY,
    total_batches INTEGER NOT NULL DEFAULT 0,
    fresh_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    total_weight_kg REAL NOT NULL DEFAULT 0.0,
    accepted_weight_kg REAL NOT NULL DEFAULT 0.0,
    total_kcal REAL NOT NULL DEFAULT 0.0,
    total_protein_g REAL NOT NULL DEFAULT 0.0,
    total_fat_g REAL NOT NULL DEFAULT 0.0,
    total_carb_g REAL NOT NULL DEFAULT 0.0,
    total_fiber_g REAL NOT NULL DEFAULT 0.0
);
"""


@contextmanager
def get_db_conn() -> Iterator[sqlite3.Connection]:
    """Mở kết nối SQLite với khóa đồng bộ thread-safe và hỗ trợ Foreign Keys."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
