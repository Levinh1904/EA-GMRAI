"""FastAPI dependencies: current user, roles, ingestion API key."""
import hmac
import logging

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import WEAK_SECRETS, settings
from app.db import get_db
from app.models import ApiKey, User
from app.security.auth import decode_access_token, hash_api_key
from app.timeutil import utcnow

logger = logging.getLogger("gmrai.auth")

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_access_token(cred.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


def ingest_identity(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Authenticate collector via API key. Returns identity dict."""
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    key_hash = hash_api_key(x_api_key)
    row = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)).first()
    if row is not None:
        row.last_used_at = utcnow()
        db.commit()
        return {"collector_id": row.name, "auth": "db_key"}
    # Bootstrap fallback from env — constant-time compare, and never accept an
    # unset/placeholder key (registry hashing above is the real path).
    if settings.api_key not in WEAK_SECRETS and hmac.compare_digest(
        x_api_key, settings.api_key
    ):
        return {"collector_id": "env-key", "auth": "env_key"}
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
