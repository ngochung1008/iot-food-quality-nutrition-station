"""Xác thực người dùng (PBKDF2-HMAC-SHA256 + HS256 JWT) và phân quyền RBAC cho 3 vai trò."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, status

from backend.core.config import settings

ROLE_ADMIN = "ADMIN"
ROLE_CHEF = "CHEF"
ROLE_RECEIVER = "RECEIVER"
ALL_ROLES = (ROLE_ADMIN, ROLE_CHEF, ROLE_RECEIVER)


def hash_password(password: str, salt: str | None = None) -> str:
    """Băm mật khẩu an toàn bằng PBKDF2-HMAC-SHA256 kèm salt ngẫu nhiên."""
    use_salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), use_salt.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256${use_salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Kiểm tra mật khẩu khớp với chuỗi băm lưu trong SQLite."""
    try:
        algo, salt, digest_hex = stored_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(dk.hex(), digest_hex)
    except Exception:
        return False


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("ascii"))


def create_access_token(user: dict[str, Any]) -> str:
    """Tạo JWT HS256 chứa thông tin định danh và vai trò người dùng."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "iat": now,
        "exp": now + settings.jwt_expire_hours * 3600,
    }
    seg_h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    seg_p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{seg_h}.{seg_p}".encode("ascii")
    sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{seg_h}.{seg_p}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Giải mã và kiểm tra chữ ký + thời hạn của JWT."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Token không đúng định dạng JWT")
        seg_h, seg_p, seg_s = parts
        signing_input = f"{seg_h}.{seg_p}".encode("ascii")
        expected_sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(seg_s)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Chữ ký JWT không hợp lệ")
        payload = json.loads(_b64url_decode(seg_p).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Phiên đăng nhập đã hết hạn")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Xác thực thất bại: {exc}",
        ) from exc


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Dependency FastAPI trích xuất người dùng hiện tại từ Bearer Token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để thực hiện thao tác này.",
        )
    token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(token)


def require_roles(*allowed_roles: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Dependency kiểm tra quyền hạn theo vai trò (ADMIN, CHEF, RECEIVER)."""

    def _checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        role = str(user.get("role", "")).upper()
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tài khoản vai trò {role} không có quyền thực hiện chức năng này.",
            )
        return user

    return _checker


def verify_admin_pin(x_admin_pin: str | None = Header(default=None, alias="X-Admin-Pin")) -> bool:
    """Kiểm tra mã PIN bổ sung nếu cấu hình ADMIN_PIN."""
    expected = settings.admin_pin
    if not expected:
        return True
    if not x_admin_pin or x_admin_pin.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mã PIN quản trị không đúng hoặc bị thiếu (Header: X-Admin-Pin).",
        )
    return True
