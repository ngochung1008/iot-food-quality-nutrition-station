"""Endpoints nghiệp vụ Bếp ăn Tập thể: Món ăn (64 lớp), Lập thực đơn -> Phiếu chuẩn bị & Cân đối chiếu."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.security import (
    ROLE_ADMIN,
    ROLE_CHEF,
    ROLE_RECEIVER,
    get_current_user,
    require_roles,
)
from backend.database.crud import (
    create_dish,
    create_procurement_order,
    delete_dish,
    get_procurement_order,
    list_dishes,
    list_procurement_orders,
)
from backend.services.station_service import station_service

router = APIRouter(prefix="/api/kitchen", tags=["Kitchen Menu & Procurement"])


class DishIngredientInput(BaseModel):
    class_name: str = Field(..., min_length=1)
    grams_per_serving: float = Field(..., gt=0.0, le=5000.0)


class CreateDishRequest(BaseModel):
    name_vi: str = Field(..., min_length=2, max_length=150)
    category: str = Field(default="Món mặn chính")
    description: str = Field(default="")
    ingredients: list[DishIngredientInput] = Field(..., min_length=1)


class CreateOrderRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    meal_date: str = Field(..., min_length=8)
    meal_shift: str = Field(default="Bữa trưa")
    servings: int = Field(..., ge=1, le=50000)
    dish_ids: list[int] = Field(..., min_length=1)
    note: str = Field(default="")
    tolerance_percent: float = Field(default=5.0, ge=0.0, le=30.0)


class CheckOrderItemRequest(BaseModel):
    item_id: str = Field(..., min_length=1)
    override_class: str | None = None
    note: str = ""


@router.get("/dishes", dependencies=[Depends(get_current_user)])
def get_dishes(search: str | None = Query(default=None), category: str | None = Query(default=None)):
    """Danh sách món ăn chuẩn kèm định lượng nguyên liệu thuộc 64 lớp YOLO26n."""
    return list_dishes(search=search, category=category)


@router.post("/dishes", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_CHEF))])
def add_dish(body: CreateDishRequest, user: dict = Depends(get_current_user)):
    """Đầu bếp tạo món ăn mới chỉ từ 64 nguyên liệu chuẩn trong dataset."""
    try:
        return create_dish(
            name_vi=body.name_vi,
            category=body.category,
            description=body.description,
            ingredients=[i.model_dump() for i in body.ingredients],
            created_by=user.get("full_name", user.get("username", "chef")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/dishes/{dish_id}", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_CHEF))])
def remove_dish(dish_id: int):
    """Ẩn món ăn khỏi thực đơn."""
    if not delete_dish(dish_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy món ăn.")
    return {"ok": True}


@router.get("/orders", dependencies=[Depends(get_current_user)])
def get_orders(status: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200)):
    """Lấy danh sách Phiếu Yêu Cầu Nguyên Liệu."""
    return list_procurement_orders(status=status, limit=limit)


@router.get("/orders/{order_id}", dependencies=[Depends(get_current_user)])
def get_order_detail(order_id: str):
    """Xem chi tiết một Phiếu Yêu Cầu Nguyên Liệu."""
    order = get_procurement_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiếu yêu cầu.")
    return order


@router.post("/orders", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_CHEF))])
def create_order(body: CreateOrderRequest, user: dict = Depends(get_current_user)):
    """Đầu bếp lập thực đơn + số suất ăn -> Tính tổng Calo & sinh Phiếu Yêu Cầu Nguyên Liệu xuống trạm cân."""
    try:
        order = create_procurement_order(
            title=body.title,
            meal_date=body.meal_date,
            meal_shift=body.meal_shift,
            servings=body.servings,
            dish_ids=body.dish_ids,
            created_by=user.get("full_name", user.get("username", "chef")),
            note=body.note,
            tolerance_percent=body.tolerance_percent,
        )
        station_service._on_station_event("order_created", {"order": order})
        return order
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/orders/{order_id}/check-item", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_CHEF, ROLE_RECEIVER))])
def check_and_complete_order_item(
    order_id: str,
    body: CheckOrderItemRequest,
    user: dict = Depends(get_current_user),
):
    """Đối chiếu kết quả cân & AI hiện tại với dòng nguyên liệu -> Tích xanh & lưu bản ghi vào CSDL."""
    try:
        return station_service.commit_current_inspection(
            override_class=body.override_class,
            note=body.note or f"Đối chiếu phiếu {order_id}",
            confirmed_by=user.get("full_name", user.get("username", "receiver")),
            order_id=order_id,
            order_item_id=body.item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
