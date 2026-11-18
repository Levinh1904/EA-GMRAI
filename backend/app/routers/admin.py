"""User administration + collector API-key management (admin only).

Design constraints, all enforced here because this is the only place accounts
are created or keys are issued:

  * The last active admin can never be demoted or disabled — otherwise the
    system locks everyone out with no in-app recovery path.
  * A user can never disable or demote themselves (avoids accidental lockout
    during a session).
  * API keys are stored as SHA-256 hashes only; the plaintext is returned once,
    at creation, and is unrecoverable afterwards.
  * Every mutation is written to SystemLog so account changes are auditable.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import WEAK_SECRETS
from app.db import get_db
from app.deps import require_admin
from app.models import ApiKey, SystemLog, User
from app.security.auth import hash_api_key, hash_password
from app.timeutil import ensure_utc

users_router = APIRouter(prefix="/users", tags=["users"])
keys_router = APIRouter(prefix="/api-keys", tags=["api-keys"])

VALID_ROLES = {"admin", "analyst", "viewer"}
MIN_PASSWORD = 10

# Same denylist as the self-service change-password route: an admin must not be
# able to create an account whose password the user could not have chosen.
_BANNED_PASSWORDS = {
    "password",
    "password123",
    "1234567890",
    "qwertyuiop",
    "admin12345",
    "changeme123",
    "gmrai12345",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=MIN_PASSWORD, max_length=256)
    role: str = Field(default="viewer")


class UserUpdateIn(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class UserResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=256)


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    role: str = Field(default="ingest")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_admin_count(db: Session, excluding_id: int | None = None) -> int:
    q = db.query(User).filter(User.role == "admin", User.is_active.is_(True))
    if excluding_id is not None:
        q = q.filter(User.id != excluding_id)
    return q.count()


def _validate_password(pw: str) -> None:
    if pw in WEAK_SECRETS or pw.lower() in _BANNED_PASSWORDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu quá yếu.")
    if pw.isdigit() or pw.isalpha():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu phải có cả chữ và số.")
    if len(set(pw)) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu lặp ký tự quá nhiều.")


def _log(db: Session, actor: str, message: str, meta: dict | None = None) -> None:
    db.add(
        SystemLog(
            level="INFO",
            component="admin",
            message=message,
            meta_json={"actor": actor, **(meta or {})},
        )
    )


def _user_payload(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": ensure_utc(u.created_at).isoformat() if u.created_at else None,
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@users_router.get("")
def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User).order_by(User.id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "users": [_user_payload(u) for u in rows],
        "active_admins": _active_admin_count(db),
    }


@users_router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Role không hợp lệ. Chọn: {', '.join(sorted(VALID_ROLES))}")
    if db.query(User).filter(User.username == body.username).first() is not None:
        raise HTTPException(409, "Username đã tồn tại.")
    _validate_password(body.password)

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    _log(db, admin.username, f"created user {body.username} (role={body.role})",
         {"target_user": body.username})
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@users_router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Không tìm thấy người dùng.")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(400, f"Role không hợp lệ. Chọn: {', '.join(sorted(VALID_ROLES))}")
        if user.id == admin.id and body.role != user.role:
            raise HTTPException(400, "Không thể tự đổi role của chính mình.")
        # Demoting the last active admin would lock the system out.
        if (
            user.role == "admin"
            and body.role != "admin"
            and _active_admin_count(db, excluding_id=user.id) == 0
        ):
            raise HTTPException(400, "Đây là admin hoạt động cuối cùng — không thể hạ quyền.")
        user.role = body.role

    if body.is_active is not None:
        if user.id == admin.id and body.is_active is False:
            raise HTTPException(400, "Không thể tự vô hiệu hoá tài khoản của mình.")
        if (
            user.role == "admin"
            and body.is_active is False
            and _active_admin_count(db, excluding_id=user.id) == 0
        ):
            raise HTTPException(400, "Đây là admin hoạt động cuối cùng — không thể vô hiệu hoá.")
        user.is_active = body.is_active

    _log(
        db,
        admin.username,
        f"updated user {user.username}",
        {"target_user": user.username, "role": user.role, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@users_router.post("/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    body: UserResetPasswordIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin password reset — the only recovery path when a user is locked out."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Không tìm thấy người dùng.")
    _validate_password(body.new_password)
    user.hashed_password = hash_password(body.new_password)
    _log(db, admin.username, f"reset password for {user.username}",
         {"target_user": user.username})
    db.commit()
    return {"status": "ok", "username": user.username}


@users_router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: int,
    purge: bool = Query(False, description="Xoá hẳn khỏi DB (mặc định chỉ vô hiệu hoá)"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deactivate by default; `?purge=true` removes the row entirely.

    Purge is opt-in because predictions/logs reference `user.id` as a plain
    integer (no FK), so a hard delete leaves those records pointing at a
    missing account. Deactivation is reversible and keeps the audit trail.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Không tìm thấy người dùng.")
    if user.id == admin.id:
        raise HTTPException(400, "Không thể xoá tài khoản của chính mình.")
    if (
        user.role == "admin"
        and user.is_active
        and _active_admin_count(db, excluding_id=user.id) == 0
    ):
        raise HTTPException(400, "Đây là admin hoạt động cuối cùng — không thể vô hiệu hoá.")

    if not purge:
        user.is_active = False
        _log(db, admin.username, f"deactivated user {user.username}",
             {"target_user": user.username})
        db.commit()
        return {"status": "ok", "username": user.username, "is_active": False, "purged": False}

    username = user.username
    db.delete(user)
    _log(db, admin.username, f"purged user {username}",
         {"target_user": username, "purged": True})
    db.commit()
    return {"status": "ok", "username": username, "purged": True}


# ---------------------------------------------------------------------------
# Collector API keys
# ---------------------------------------------------------------------------

def _new_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "gmrai_" + "".join(secrets.choice(alphabet) for _ in range(40))


def _mask(key_hash: str) -> str:
    """Show only a stable prefix so keys are identifiable without exposing them."""
    return f"sha256:{key_hash[:8]}…"


@keys_router.get("")
def list_keys(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(ApiKey).order_by(ApiKey.id).all()
    return {
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "role": k.role,
                "is_active": k.is_active,
                "fingerprint": _mask(k.key_hash),
                "last_used_at": ensure_utc(k.last_used_at).isoformat() if k.last_used_at else None,
                "created_at": ensure_utc(k.created_at).isoformat() if k.created_at else None,
            }
            for k in rows
        ]
    }


@keys_router.post("", status_code=status.HTTP_201_CREATED)
def create_key(
    body: ApiKeyCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Returns the plaintext key ONCE — it is stored only as a hash."""
    if db.query(ApiKey).filter(ApiKey.name == body.name).first() is not None:
        raise HTTPException(409, "Tên key đã tồn tại.")
    plaintext = _new_key()
    key = ApiKey(
        name=body.name,
        key_hash=hash_api_key(plaintext),
        role=body.role,
        is_active=True,
    )
    db.add(key)
    _log(db, admin.username, f"created api key {body.name}", {"key_name": body.name})
    db.commit()
    db.refresh(key)
    return {
        "id": key.id,
        "name": key.name,
        "role": key.role,
        "api_key": plaintext,
        "note": "Lưu key này ngay — chỉ hiển thị một lần, không thể xem lại.",
    }


@keys_router.delete("/{key_id}")
def revoke_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(404, "Không tìm thấy API key.")
    if key.name == "env-bootstrap":
        raise HTTPException(
            400,
            "Không thể thu hồi key bootstrap từ env — đổi GMRAI_API_KEY trong backend/.env thay thế.",
        )
    key.is_active = False
    _log(db, admin.username, f"revoked api key {key.name}", {"key_name": key.name})
    db.commit()
    return {"status": "ok", "name": key.name, "is_active": False}


@keys_router.post("/{key_id}/restore")
def restore_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(404, "Không tìm thấy API key.")
    key.is_active = True
    _log(db, admin.username, f"restored api key {key.name}", {"key_name": key.name})
    db.commit()
    return {"status": "ok", "name": key.name, "is_active": True}
