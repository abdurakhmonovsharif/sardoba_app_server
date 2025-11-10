import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///" + str(BASE_DIR / "test.db"))
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-secret")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("OTP_EXPIRATION_MINUTES", "5")
os.environ.setdefault("OTP_RATE_LIMIT_PER_HOUR", "10")

from app.core.config import get_settings
from app.core import db as db_module
from app.core.dependencies import get_db
from app.models import Base
from app.main import app

get_settings.cache_clear()

db_module._engine = None
db_module._SessionLocal = None
_db_path = BASE_DIR / "test.db"


def _create_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
    return create_engine(settings.DATABASE_URL, connect_args=connect_args)


def _create_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session")
def engine():
    engine = _create_engine()
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    if _db_path.exists():
        _db_path.unlink()


@pytest.fixture(scope="session")
def session_factory(engine):
    return _create_session_factory(engine)


@pytest.fixture()
def db_session(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(session_factory):
    def _get_test_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
