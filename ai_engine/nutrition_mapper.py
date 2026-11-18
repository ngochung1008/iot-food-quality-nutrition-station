"""Ánh xạ 64 nhãn thực phẩm YOLO26n (FISH dataset) sang bảng thành phần dinh dưỡng chuẩn (per 100g).

Kết hợp dữ liệu chính thức từ Bảng Thành Phần Thực Phẩm Việt Nam (VTN_FCT_2007 - Viện Dinh Dưỡng)
và chuẩn dinh dưỡng quốc tế cho đầy đủ 64 lớp nhận diện của mô hình YOLO26n.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger("nutrition_station.ai.nutrition_mapper")


@dataclass(frozen=True)
class FoodNutritionProfile:
    """Hồ sơ dinh dưỡng chuẩn trên 100g phần ăn được của một loại thực phẩm."""

    class_name: str
    code: str
    vietnamese_name: str
    food_group: str
    edible_portion_percent: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrate_g: float
    fiber_g: float
    calcium_mg: float = 0.0
    iron_mg: float = 0.0
    vitamin_c_mg: float = 0.0
    source: str = "VTN_FCT_2007 / USDA"

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "code": self.code,
            "vietnamese_name": self.vietnamese_name,
            "food_group": self.food_group,
            "edible_portion_percent": self.edible_portion_percent,
            "per_100g": {
                "energy_kcal": self.energy_kcal,
                "protein_g": self.protein_g,
                "fat_g": self.fat_g,
                "carbohydrate_g": self.carbohydrate_g,
                "fiber_g": self.fiber_g,
                "calcium_mg": self.calcium_mg,
                "iron_mg": self.iron_mg,
                "vitamin_c_mg": self.vitamin_c_mg,
            },
            "source": self.source,
        }


# Bảng dữ liệu chuẩn per 100g cho toàn bộ 64 classes của model.ncnn (metadata.yaml)
# Các mục có trong data/datasets_curated/nutrition/vtn_fct_2007.json được đối chiếu chuẩn xác.
NUTRITION_TABLE_64: dict[str, FoodNutritionProfile] = {
    "Apple": FoodNutritionProfile("Apple", "APPLE", "Táo tây", "Trái cây", 88.0, 52.0, 0.3, 0.2, 13.8, 2.4, 6.0, 0.12, 4.6),
    "Apricot": FoodNutritionProfile("Apricot", "APRICOT", "Quả mơ", "Trái cây", 92.0, 48.0, 1.4, 0.4, 11.1, 2.0, 13.0, 0.39, 10.0),
    "Asparagus": FoodNutritionProfile("Asparagus", "ASPARAGUS", "Măng tây", "Rau, củ, quả", 75.0, 20.0, 2.2, 0.1, 3.9, 2.1, 24.0, 2.14, 5.6),
    "Avocado": FoodNutritionProfile("Avocado", "AVOCADO", "Quả bơ", "Trái cây", 74.0, 160.0, 2.0, 14.7, 8.5, 6.7, 12.0, 0.55, 10.0),
    "Banana": FoodNutritionProfile("Banana", "BANANA", "Chuối tiêu", "Trái cây", 68.0, 89.0, 1.1, 0.3, 22.8, 2.6, 5.0, 0.26, 8.7),
    "Beef": FoodNutritionProfile("Beef", "BEEF", "Thịt bò nạc (loại 1)", "Thịt và sản phẩm từ thịt", 100.0, 182.0, 21.5, 10.7, 0.0, 0.0, 12.0, 3.1, 0.0, "VTN_FCT_2007 (01015)"),
    "Beetroot": FoodNutritionProfile("Beetroot", "BEETROOT", "Củ dền đỏ", "Rau, củ, quả", 82.0, 43.0, 1.6, 0.2, 9.6, 2.8, 16.0, 0.80, 4.9),
    "Bell Pepper": FoodNutritionProfile("Bell Pepper", "BELL_PEPPER", "Ớt chuông", "Rau, củ, quả", 84.0, 31.0, 1.0, 0.3, 6.0, 2.1, 7.0, 0.43, 127.7),
    "Berry": FoodNutritionProfile("Berry", "BERRY", "Dâu / Quả mọng", "Trái cây", 95.0, 43.0, 0.9, 0.4, 9.8, 3.5, 18.0, 0.45, 48.0),
    "Cabbage": FoodNutritionProfile("Cabbage", "CABBAGE", "Bắp cải trắng", "Rau, củ, quả", 85.0, 29.0, 1.8, 0.2, 5.4, 1.6, 48.0, 1.1, 30.0, "VTN_FCT_2007 (03008)"),
    "Cantaloupe": FoodNutritionProfile("Cantaloupe", "CANTALOUPE", "Dưa lưới", "Trái cây", 65.0, 34.0, 0.8, 0.2, 8.2, 0.9, 9.0, 0.21, 36.7),
    "Carrot": FoodNutritionProfile("Carrot", "CARROT", "Cà rốt", "Rau, củ, quả", 84.0, 39.0, 1.5, 0.2, 7.8, 1.2, 43.0, 0.8, 7.0, "VTN_FCT_2007 (03022)"),
    "Cashew Nut": FoodNutritionProfile("Cashew Nut", "CASHEW_NUT", "Hạt điều", "Đậu, hạt", 100.0, 553.0, 18.2, 43.9, 30.2, 3.3, 37.0, 6.68, 0.5),
    "Cauliflower": FoodNutritionProfile("Cauliflower", "CAULIFLOWER", "Súp lơ trắng", "Rau, củ, quả", 72.0, 25.0, 1.9, 0.3, 5.0, 2.0, 22.0, 0.42, 48.2),
    "Cherry": FoodNutritionProfile("Cherry", "CHERRY", "Quả anh đào (Cherry)", "Trái cây", 90.0, 63.0, 1.1, 0.2, 16.0, 2.1, 13.0, 0.36, 7.0),
    "Cherry Tomato": FoodNutritionProfile("Cherry Tomato", "CHERRY_TOMATO", "Cà chua bi", "Rau, củ, quả", 98.0, 18.0, 0.9, 0.2, 3.9, 1.2, 10.0, 0.27, 13.7),
    "Chestnut": FoodNutritionProfile("Chestnut", "CHESTNUT", "Hạt dẻ", "Đậu, hạt", 80.0, 213.0, 2.4, 2.3, 45.5, 8.1, 27.0, 1.01, 43.0),
    "Chicken": FoodNutritionProfile("Chicken", "CHICKEN", "Thịt gà tươi", "Thịt và sản phẩm từ thịt", 78.0, 165.0, 20.5, 8.8, 0.0, 0.0, 11.0, 1.1, 0.0),
    "Coconut": FoodNutritionProfile("Coconut", "COCONUT", "Dừa tươi (cơm dừa)", "Trái cây", 52.0, 354.0, 3.3, 33.5, 15.2, 9.0, 14.0, 2.43, 3.3),
    "Corn": FoodNutritionProfile("Corn", "CORN", "Ngô ngọt (Bắp)", "Ngũ cốc và rau củ", 65.0, 86.0, 3.3, 1.4, 18.7, 2.0, 2.0, 0.52, 6.8),
    "Crab": FoodNutritionProfile("Crab", "CRAB", "Cua biển tươi", "Thủy sản và hải sản", 45.0, 87.0, 18.1, 1.1, 0.0, 0.0, 89.0, 0.74, 3.0),
    "Cucumber": FoodNutritionProfile("Cucumber", "CUCUMBER", "Dưa chuột (Dưa leo)", "Rau, củ, quả", 94.0, 15.0, 0.7, 0.1, 3.6, 0.5, 16.0, 0.28, 2.8),
    "Date": FoodNutritionProfile("Date", "DATE", "Chà là", "Trái cây", 88.0, 277.0, 1.8, 0.2, 75.0, 6.7, 64.0, 0.90, 0.0),
    "Dragon Fruit": FoodNutritionProfile("Dragon Fruit", "DRAGON_FRUIT", "Thanh long", "Trái cây", 70.0, 50.0, 1.1, 0.4, 11.0, 3.0, 8.5, 1.9, 20.5),
    "Egg": FoodNutritionProfile("Egg", "EGG", "Trứng gà toàn phần", "Trứng và sản phẩm từ trứng", 88.0, 166.0, 14.8, 11.6, 0.5, 0.0, 55.0, 2.7, 0.0, "VTN_FCT_2007 (04001)"),
    "Eggplant": FoodNutritionProfile("Eggplant", "EGGPLANT", "Cà tím", "Rau, củ, quả", 87.0, 25.0, 1.0, 0.2, 5.9, 3.0, 9.0, 0.23, 2.2),
    "Fig": FoodNutritionProfile("Fig", "FIG", "Quả sung / Vả", "Trái cây", 95.0, 74.0, 0.8, 0.3, 19.2, 2.9, 35.0, 0.37, 2.0),
    "Fish": FoodNutritionProfile("Fish", "FISH", "Cá phi lê (cá basa/trắm)", "Thủy sản và hải sản", 80.0, 124.0, 17.1, 4.0, 0.2, 0.0, 25.0, 1.1, 0.0, "VTN_FCT_2007 (02018)"),
    "Garlic": FoodNutritionProfile("Garlic", "GARLIC", "Tỏi củ", "Gia vị / Rau củ", 87.0, 149.0, 6.4, 0.5, 33.1, 2.1, 181.0, 1.7, 31.2),
    "Ginger": FoodNutritionProfile("Ginger", "GINGER", "Gừng tươi", "Gia vị / Rau củ", 85.0, 80.0, 1.8, 0.8, 17.8, 2.0, 16.0, 0.6, 5.0),
    "Grape": FoodNutritionProfile("Grape", "GRAPE", "Nho tươi", "Trái cây", 94.0, 69.0, 0.7, 0.2, 18.1, 0.9, 10.0, 0.36, 3.2),
    "Grapefruit": FoodNutritionProfile("Grapefruit", "GRAPEFRUIT", "Bưởi", "Trái cây", 60.0, 42.0, 0.8, 0.1, 10.7, 1.6, 22.0, 0.08, 31.2),
    "Green Beans": FoodNutritionProfile("Green Beans", "GREEN_BEANS", "Đậu cô ve (Đậu que)", "Rau, củ, quả", 90.0, 31.0, 1.8, 0.2, 7.0, 2.7, 37.0, 1.03, 12.2),
    "Guava": FoodNutritionProfile("Guava", "GUAVA", "Quả ổi", "Trái cây", 92.0, 68.0, 2.6, 1.0, 14.3, 5.4, 18.0, 0.26, 228.3),
    "Kiwi": FoodNutritionProfile("Kiwi", "KIWI", "Quả Kiwi", "Trái cây", 85.0, 61.0, 1.1, 0.5, 14.7, 3.0, 34.0, 0.31, 92.7),
    "Lamb": FoodNutritionProfile("Lamb", "LAMB", "Thịt cừu", "Thịt và sản phẩm từ thịt", 92.0, 258.0, 16.9, 20.6, 0.0, 0.0, 10.0, 1.55, 0.0),
    "Leek": FoodNutritionProfile("Leek", "LEEK", "Tỏi tây (Hành boa-rô)", "Rau, củ, quả", 75.0, 61.0, 1.5, 0.3, 14.2, 1.8, 59.0, 2.1, 12.0),
    "Lemon": FoodNutritionProfile("Lemon", "LEMON", "Chanh vàng", "Trái cây", 65.0, 29.0, 1.1, 0.3, 9.3, 2.8, 26.0, 0.6, 53.0),
    "Lime": FoodNutritionProfile("Lime", "LIME", "Chanh xanh", "Trái cây", 70.0, 30.0, 0.7, 0.2, 10.5, 2.8, 33.0, 0.6, 29.1),
    "Lobster": FoodNutritionProfile("Lobster", "LOBSTER", "Tôm hùm", "Thủy sản và hải sản", 45.0, 89.0, 19.0, 0.9, 0.5, 0.0, 96.0, 0.3, 0.0),
    "Lychee": FoodNutritionProfile("Lychee", "LYCHEE", "Quả vải", "Trái cây", 65.0, 66.0, 0.8, 0.4, 16.5, 1.3, 5.0, 0.31, 71.5),
    "Mango": FoodNutritionProfile("Mango", "MANGO", "Xoài chín", "Trái cây", 72.0, 60.0, 0.8, 0.4, 15.0, 1.6, 11.0, 0.16, 36.4),
    "Mangosteen": FoodNutritionProfile("Mangosteen", "MANGOSTEEN", "Măng cụt", "Trái cây", 35.0, 73.0, 0.4, 0.6, 17.9, 1.8, 12.0, 0.3, 2.9),
    "Mushroom": FoodNutritionProfile("Mushroom", "MUSHROOM", "Nấm tươi", "Rau, củ, quả", 96.0, 22.0, 3.1, 0.3, 3.3, 1.0, 3.0, 0.5, 2.1),
    "Nectarine": FoodNutritionProfile("Nectarine", "NECTARINE", "Quả xuân đào", "Trái cây", 91.0, 44.0, 1.1, 0.3, 10.6, 1.7, 6.0, 0.28, 5.4),
    "Orange": FoodNutritionProfile("Orange", "ORANGE", "Cam sành / Cam tươi", "Trái cây", 73.0, 47.0, 0.9, 0.1, 11.8, 2.4, 40.0, 0.1, 53.2),
    "Passion Fruit": FoodNutritionProfile("Passion Fruit", "PASSION_FRUIT", "Chanh dây", "Trái cây", 52.0, 97.0, 2.2, 0.7, 23.4, 10.4, 12.0, 1.6, 30.0),
    "Peach": FoodNutritionProfile("Peach", "PEACH", "Quả đào", "Trái cây", 89.0, 39.0, 0.9, 0.3, 9.5, 1.5, 6.0, 0.25, 6.6),
    "Pear": FoodNutritionProfile("Pear", "PEAR", "Quả lê", "Trái cây", 90.0, 57.0, 0.4, 0.1, 15.2, 3.1, 9.0, 0.18, 4.3),
    "Pineapple": FoodNutritionProfile("Pineapple", "PINEAPPLE", "Dứa (Thơm)", "Trái cây", 55.0, 50.0, 0.5, 0.1, 13.1, 1.4, 13.0, 0.29, 47.8),
    "Plum": FoodNutritionProfile("Plum", "PLUM", "Quả mận", "Trái cây", 94.0, 46.0, 0.7, 0.3, 11.4, 1.4, 6.0, 0.17, 9.5),
    "Pomegranate": FoodNutritionProfile("Pomegranate", "POMEGRANATE", "Quả lựu", "Trái cây", 56.0, 83.0, 1.7, 1.2, 18.7, 4.0, 10.0, 0.3, 10.2),
    "Pork": FoodNutritionProfile("Pork", "PORK", "Thịt lợn nạc (Thịt heo)", "Thịt và sản phẩm từ thịt", 100.0, 139.0, 19.0, 7.0, 0.0, 0.0, 7.0, 1.0, 0.0, "VTN_FCT_2007 (01001)"),
    "Potato": FoodNutritionProfile("Potato", "POTATO", "Khoai tây", "Rau, củ, quả", 84.0, 77.0, 2.0, 0.1, 17.5, 2.2, 12.0, 0.78, 19.7),
    "Rambutan": FoodNutritionProfile("Rambutan", "RAMBUTAN", "Chôm chôm", "Trái cây", 48.0, 82.0, 0.7, 0.2, 20.9, 0.9, 22.0, 0.35, 4.9),
    "Red Onion": FoodNutritionProfile("Red Onion", "RED_ONION", "Hành tím", "Gia vị / Rau củ", 90.0, 40.0, 1.1, 0.1, 9.3, 1.7, 23.0, 0.21, 7.4),
    "Shrimp": FoodNutritionProfile("Shrimp", "SHRIMP", "Tôm tươi", "Thủy sản và hải sản", 62.0, 85.0, 20.1, 0.5, 0.0, 0.0, 64.0, 0.5, 0.0),
    "Star Fruit": FoodNutritionProfile("Star Fruit", "STAR_FRUIT", "Quả khế", "Trái cây", 94.0, 31.0, 1.0, 0.3, 6.7, 2.8, 3.0, 0.08, 34.4),
    "Sweet Potato": FoodNutritionProfile("Sweet Potato", "SWEET_POTATO", "Khoai lang", "Rau, củ, quả", 85.0, 86.0, 1.6, 0.1, 20.1, 3.0, 30.0, 0.61, 2.4),
    "Tomato": FoodNutritionProfile("Tomato", "TOMATO", "Cà chua chín", "Rau, củ, quả", 95.0, 20.0, 0.6, 0.2, 4.2, 0.8, 12.0, 1.4, 40.0, "VTN_FCT_2007 (03015)"),
    "Walnut": FoodNutritionProfile("Walnut", "WALNUT", "Hạt óc chó", "Đậu, hạt", 45.0, 654.0, 15.2, 65.2, 13.7, 6.7, 98.0, 2.91, 1.3),
    "Watermelon": FoodNutritionProfile("Watermelon", "WATERMELON", "Dưa hấu đỏ", "Trái cây", 62.0, 30.0, 0.6, 0.2, 7.6, 0.4, 7.0, 0.24, 8.1),
    "White Onion": FoodNutritionProfile("White Onion", "WHITE_ONION", "Hành tây trắng", "Rau, củ, quả", 90.0, 40.0, 1.1, 0.1, 9.3, 1.7, 23.0, 0.21, 7.4),
    "Zucchini": FoodNutritionProfile("Zucchini", "ZUCCHINI", "Bí ngòi xanh", "Rau, củ, quả", 92.0, 17.0, 1.2, 0.3, 3.1, 1.0, 16.0, 0.37, 17.9),
}


def load_vtn_fct_reference(path: Path | None = None) -> list[dict[str, Any]]:
    """Đọc dữ liệu tham khảo từ file vtn_fct_2007.json trong thư mục data/."""
    target = path or settings.vtn_fct_path
    if not target.exists():
        return []
    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("food_items", [])
    except Exception as exc:
        logger.warning(f"Không thể đọc {target}: {exc}")
        return []


def normalize_label(label: str) -> str:
    """Chuẩn hóa nhãn từ model (bỏ tiền tố Fresh_/Rotten_) để tra cứu dinh dưỡng."""
    if not label:
        return "Unknown"
    cleaned = label.strip()
    for prefix in ("Fresh_", "Rotten_", "fresh_", "rotten_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned.strip()


def get_nutrition_profile(label: str) -> FoodNutritionProfile | None:
    """Tra cứu hồ sơ dinh dưỡng chuẩn per 100g theo tên nhãn YOLO26n."""
    clean = normalize_label(label)
    if not clean or clean == "Unknown":
        return None
    if clean in NUTRITION_TABLE_64:
        return NUTRITION_TABLE_64[clean]

    lower = clean.lower()
    for key, profile in NUTRITION_TABLE_64.items():
        if key.lower() == lower or profile.code.lower() == lower or profile.vietnamese_name.lower() == lower:
            return profile
    return None


def list_all_nutrition_profiles() -> list[dict[str, Any]]:
    """Trả về toàn bộ bảng thành phần dinh dưỡng của 64 nhãn."""
    return [profile.to_dict() for profile in NUTRITION_TABLE_64.values()]
