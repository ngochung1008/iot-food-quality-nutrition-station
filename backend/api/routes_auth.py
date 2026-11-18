"""Endpoints xác thực người dùng (Login JWT) và quản lý tài khoản nhân viên (RBAC Admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.security import (
    ALL_ROLES,
    ROLE_ADMIN,
    create_access_token,
    get_current_user,
    require_roles,
    verify_password,
)
from backend.database.crud import (
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    update_user,
)

router = APIRouter(tags=["Authentication & Users"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=4, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: str = Field(...)


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: bool | None = None


@router.post("/api/auth/login")
def login(body: LoginRequest):
    """Đăng nhập hệ thống và cấp phát JWT Bearer Token."""
    user = get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị tạm khóa. Vui lòng liên hệ Quản trị viên.",
        )

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
    }


@router.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    """Lấy thông tin người dùng đang đăng nhập từ JWT."""
    return {"user": user}


@router.get("/api/users", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def get_users_list():
    """Danh sách toàn bộ tài khoản nhân viên (Chỉ Admin)."""
    return list_users()


@router.post("/api/users", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def add_user(body: CreateUserRequest):
    """Tạo tài khoản nhân viên mới (Chỉ Admin)."""
    role_up = body.role.strip().upper()
    if role_up not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Vai trò phải thuộc {ALL_ROLES}.")
    if get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại.")
    return create_user(body.username, body.password, body.full_name, role_up)


@router.put("/api/users/{user_id}", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def edit_user(user_id: int, body: UpdateUserRequest):
    """Cập nhật thông tin hoặc phân quyền nhân viên (Chỉ Admin)."""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "role" in fields and fields["role"].strip().upper() not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Vai trò phải thuộc {ALL_ROLES}.")
    updated = update_user(user_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    return updated


@router.delete("/api/users/{user_id}", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def remove_user(user_id: int, current: dict = Depends(get_current_user)):
    """Xóa tài khoản nhân viên (không thể tự xóa chính mình)."""
    if str(user_id) == str(current.get("sub")):
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản đang đăng nhập.")
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    return {"ok": True, "deleted_id": user_id}
