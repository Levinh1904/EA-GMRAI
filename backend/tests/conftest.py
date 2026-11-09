"""Shared pytest fixtures: isolated in-memory DB + TestClient."""
import os

os.environ.setdefault("GMRAI_LOGIN_RATE_LIMIT", "1000/minute")
os.environ.setdefault("GMRAI_AUTOMATION_ENABLED", "false")
os.environ.setdefault("GMRAI_ARTIFACT_DIR", "/tmp/gmrai_test_artifacts")
os.environ.setdefault("GMRAI_SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.db import Base, init_engine, reset_engine, session
from app.models import User
from app.security.auth import hash_password

ADMIN = {"username": "admin", "password": "admin-pass"}
ANALYST = {"username": "analyst", "password": "analyst-pass"}


@pytest.fixture()
def db():
    reset_engine()
    engine = init_engine("sqlite://", pool_class=StaticPool)
    Base.metadata.create_all(engine)
    with session() as s:
        s.add(User(username=ADMIN["username"], hashed_password=hash_password(ADMIN["password"]), role="admin"))
        s.add(User(username=ANALYST["username"], hashed_password=hash_password(ANALYST["password"]), role="analyst"))
        s.commit()
    yield
    reset_engine()


@pytest.fixture()
def client(db):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_token(client):
    r = client.post("/api/v1/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def analyst_token(client):
    r = client.post("/api/v1/auth/login", json=ANALYST)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
