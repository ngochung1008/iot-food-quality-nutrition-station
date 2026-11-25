"""Endpoints quản lý danh mục 64 loại thực phẩm và bảng thành phần dinh dưỡng chuẩn."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.security import ROLE_ADMIN, ROLE_CHEF, require_roles, verify_admin_pin
from backend.database.crud import list_foods, update_food_nutrition
from backend.services.nutrition_service import calculate_nutrition

router = APIRouter(prefix="/api/foods", tags=["Foods & Nutrition"])


class FoodUpdateRequest(BaseModel):
    vietnamese_name: str | None = None
    food_group: str | None = None
    edible_portion_percent: float | None = Field(default=None, gt=0.0, le=100.0)
    energy_kcal: float | None = Field(default=None, ge=0.0)
    protein_g: float | None = Field(default=None, ge=0.0)
    fat_g: float | None = Field(default=None, ge=0.0)
    carbohydrate_g: float | None = Field(default=None, ge=0.0)
    fiber_g: float | None = Field(default=None, ge=0.0)
    calcium_mg: float | None = Field(default=None, ge=0.0)
    iron_mg: float | None = Field(default=None, ge=0.0)
    vitamin_c_mg: float | None = Field(default=None, ge=0.0)
    unit_price_vnd_per_kg: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


@router.get("")
def get_foods(
    search: str | None = Query(default=None),
    food_group: str | None = Query(default=None),
):
    """Lấy danh sách bảng thành phần dinh dưỡng chuẩn (per 100g) cho 64 nhãn YOLO26n."""
    return list_foods(search=search, food_group=food_group)


@router.get("/calculate")
def preview_nutrition_calculation(
    class_name: str = Query(...),
    weight_gram: float = Query(..., ge=0.0),
    use_edible_portion: bool = Query(default=True),
):
    """Tính toán thử giá trị dinh dưỡng cho một loại thực phẩm và khối lượng bất kỳ."""
    return calculate_nutrition(class_name, weight_gram, use_edible_portion=use_edible_portion)


@router.put("/{food_id}", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_CHEF)), Depends(verify_admin_pin)])
def update_food(food_id: int, body: FoodUpdateRequest):
    """Cập nhật thông số dinh dưỡng của một loại thực phẩm."""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = update_food_nutrition(food_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy thực phẩm.")
    return updated
