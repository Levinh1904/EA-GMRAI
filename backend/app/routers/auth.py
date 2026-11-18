from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.config import WEAK_SECRETS, settings
from app.db import get_db
from app.deps import get_current_user
from app.models import SystemLog, User
from app.schemas import LoginIn, PasswordChangeIn, TokenOut
from app.rate_limit import limiter
from app.security.auth import create_access_token, hash_password, verify_password

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# Reject trivially guessable passwords even when they clear the length check.
_BANNED_PASSWORDS = {
    "password",
    "password123",
    "1234567890",
    "qwertyuiop",
    "admin12345",
    "changeme123",
    "gmrai12345",
}


def _validate_new_password(pw: str) -> None:
    if pw in WEAK_SECRETS or pw.lower() in _BANNED_PASSWORDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mật khẩu mới quá yếu — chọn mật khẩu khác.",
        )
    if pw.isdigit() or pw.isalpha():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mật khẩu mới phải có cả chữ và số.",
        )
    if len(set(pw)) < 6:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mật khẩu mới lặp ký tự quá nhiều — chọn mật khẩu khác.",
        )


@auth_router.post("/login", response_model=TokenOut)
@limiter.limit(settings.login_rate_limit)
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        db.add(
            SystemLog(
                level="WARNING",
                component="auth",
                message=f"failed login for {body.username}",
            )
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")
    token = create_access_token(user.id, user.username, user.role)
    return TokenOut(access_token=token, username=user.username, role=user.role)


@auth_router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role, "is_active": user.is_active}


@auth_router.post("/change-password")
@limiter.limit(settings.password_change_rate_limit)
def change_password(
    request: Request,
    body: PasswordChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the signed-in user's own password.

    Requires the CURRENT password (a stolen token alone must not be enough),
    rejects weak new passwords, and logs the event. The returned access token
    is reissued so the client keeps working after the change.
    """
    if not verify_password(body.current_password, user.hashed_password):
        db.add(
            SystemLog(
                level="WARNING",
                component="auth",
                message=f"failed password change for {user.username}",
            )
        )
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mật khẩu hiện tại không đúng.")

    if body.new_password != body.confirm_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Mật khẩu xác nhận không khớp."
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Mật khẩu mới phải khác mật khẩu hiện tại."
        )
    _validate_new_password(body.new_password)

    user.hashed_password = hash_password(body.new_password)
    db.add(
        SystemLog(
            level="INFO",
            component="auth",
            message=f"password changed for {user.username}",
        )
    )
    db.commit()

    return {
        "status": "ok",
        "username": user.username,
        "access_token": create_access_token(user.id, user.username, user.role),
        "token_type": "bearer",
    }
