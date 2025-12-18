import os
import sys
from pathlib import Path

import pytest
import anyio
import httpx
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
os.environ.setdefault("ESKIZ_LOGIN", "test@example.com")
os.environ.setdefault("ESKIZ_PASSWORD", "test-password")
os.environ.setdefault("SMS_DRY_RUN", "true")
os.environ.setdefault("IIKO_API_BASE_URL", "http://127.0.0.1:1")
os.environ.setdefault("IIKO_API_LOGIN", "test-iiko-login")
os.environ.setdefault("IIKO_ORGANIZATION_ID", "test-org")

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

    class _SyncASGIClient:
        def __init__(self, fastapi_app):
            self._client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=fastapi_app),
                base_url="http://testserver",
            )

        def request(self, method: str, url: str, **kwargs):
            async def _do_request():
                return await self._client.request(method, url, **kwargs)

            return anyio.run(_do_request)

        def get(self, url: str, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url: str, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url: str, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url: str, **kwargs):
            return self.request("DELETE", url, **kwargs)

        def close(self):
            async def _do_close():
                await self._client.aclose()

            anyio.run(_do_close)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()

    with _SyncASGIClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
