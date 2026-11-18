"""Dịch vụ tính toán thành phần dinh dưỡng thực tế từ khối lượng cân (g -> kcal/protein/lipid/carb)."""

from __future__ import annotations

from typing import Any

from ai_engine.nutrition_mapper import get_nutrition_profile, normalize_label
from backend.core.constants import (
    DAILY_REF_CARB_G,
    DAILY_REF_FAT_G,
    DAILY_REF_KCAL,
    DAILY_REF_PROTEIN_G,
)
from backend.database.crud import get_food_by_label


def calculate_nutrition(label: str, weight_gram: float, use_edible_portion: bool = True) -> dict[str, Any]:
    """Quy đổi khối lượng cân được (gram) sang giá trị dinh dưỡng chi tiết."""
    clean_label = normalize_label(label)
    weight_g = max(0.0, float(weight_gram))

    # Ưu tiên lấy từ SQLite (cho phép quản trị viên tùy chỉnh giá trị thực tế), fallback sang bảng chuẩn 64 lớp
    food_row = get_food_by_label(clean_label)
    if food_row is None:
        profile = get_nutrition_profile(clean_label)
        if profile is not None:
            food_row = {
                "code": profile.code,
                "class_name": profile.class_name,
                "vietnamese_name": profile.vietnamese_name,
                "food_group": profile.food_group,
                "edible_portion_percent": profile.edible_portion_percent,
                "energy_kcal": profile.energy_kcal,
                "protein_g": profile.protein_g,
                "fat_g": profile.fat_g,
                "carbohydrate_g": profile.carbohydrate_g,
                "fiber_g": profile.fiber_g,
                "calcium_mg": profile.calcium_mg,
                "iron_mg": profile.iron_mg,
                "vitamin_c_mg": profile.vitamin_c_mg,
                "source": profile.source,
            }

    if food_row is None:
        return {
            "matched": False,
            "code": "UNKNOWN",
            "class_name": clean_label or "Unknown",
            "vietnamese_name": "Chưa nhận diện rõ loại thực phẩm",
            "food_group": "Chưa phân loại",
            "weight_gram": round(weight_g, 1),
            "edible_portion_percent": 100.0,
            "edible_gram": round(weight_g, 1),
            "per_100g": {},
            "actual": {
                "energy_kcal": 0.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "carbohydrate_g": 0.0,
                "fiber_g": 0.0,
                "calcium_mg": 0.0,
                "iron_mg": 0.0,
                "vitamin_c_mg": 0.0,
            },
            "daily_percent": {
                "kcal_pct": 0.0,
                "protein_pct": 0.0,
                "fat_pct": 0.0,
                "carb_pct": 0.0,
            },
            "source": "N/A",
        }

    edible_pct = float(food_row.get("edible_portion_percent", 100.0))
    edible_gram = weight_g * (edible_pct / 100.0) if use_edible_portion else weight_g
    factor = edible_gram / 100.0

    kcal = round(float(food_row["energy_kcal"]) * factor, 1)
    protein = round(float(food_row["protein_g"]) * factor, 2)
    fat = round(float(food_row["fat_g"]) * factor, 2)
    carb = round(float(food_row["carbohydrate_g"]) * factor, 2)
    fiber = round(float(food_row["fiber_g"]) * factor, 2)
    calcium = round(float(food_row["calcium_mg"]) * factor, 1)
    iron = round(float(food_row["iron_mg"]) * factor, 2)
    vit_c = round(float(food_row["vitamin_c_mg"]) * factor, 1)

    return {
        "matched": True,
        "code": food_row["code"],
        "class_name": food_row["class_name"],
        "vietnamese_name": food_row["vietnamese_name"],
        "food_group": food_row["food_group"],
        "weight_gram": round(weight_g, 1),
        "edible_portion_percent": round(edible_pct, 1),
        "edible_gram": round(edible_gram, 1),
        "per_100g": {
            "energy_kcal": float(food_row["energy_kcal"]),
            "protein_g": float(food_row["protein_g"]),
            "fat_g": float(food_row["fat_g"]),
            "carbohydrate_g": float(food_row["carbohydrate_g"]),
            "fiber_g": float(food_row["fiber_g"]),
            "calcium_mg": float(food_row["calcium_mg"]),
            "iron_mg": float(food_row["iron_mg"]),
            "vitamin_c_mg": float(food_row["vitamin_c_mg"]),
        },
        "actual": {
            "energy_kcal": kcal,
            "protein_g": protein,
            "fat_g": fat,
            "carbohydrate_g": carb,
            "fiber_g": fiber,
            "calcium_mg": calcium,
            "iron_mg": iron,
            "vitamin_c_mg": vit_c,
        },
        "daily_percent": {
            "kcal_pct": round((kcal / DAILY_REF_KCAL) * 100.0, 1),
            "protein_pct": round((protein / DAILY_REF_PROTEIN_G) * 100.0, 1),
            "fat_pct": round((fat / DAILY_REF_FAT_G) * 100.0, 1),
            "carb_pct": round((carb / DAILY_REF_CARB_G) * 100.0, 1),
        },
        "source": food_row.get("source", "VTN_FCT_2007"),
    }
