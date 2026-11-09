from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import SystemLog, User
from app.schemas import LoginIn, TokenOut
from app.security.auth import create_access_token, verify_password

limiter = Limiter(key_func=get_remote_address)
auth_router = APIRouter(prefix="/auth", tags=["auth"])


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
