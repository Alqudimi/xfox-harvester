"""Shared pytest fixtures.

A dedicated PostgreSQL database (``xfox_test``) runs on the sandbox's pgserver
instance. The database URL is injected BEFORE any xfox import so the
lazily-created engine binds to it. Each test gets a fresh engine bound to its
own event loop (asyncpg connections are loop-bound) with a clean schema.
"""

from __future__ import annotations

import os

# --- must run before importing xfox ---
_TEST_DB = "xfox_test"
_PG_HOST = "/home/z/my-project/.pgdata"
os.environ["XFOX_DATABASE_URL"] = f"postgresql+asyncpg://postgres:@/{_TEST_DB}?host={_PG_HOST}"
os.environ["XFOX_DATA_DIR"] = "/tmp/xfox-test-data"
os.environ["XFOX_SECRET_KEY"] = "test-secret-key-for-pytest-only-000000000000"
os.environ["XFOX_ENVIRONMENT"] = "development"

import pgserver  # noqa: E402

_server = pgserver.get_server(pgdata=_PG_HOST, cleanup_mode=None)


def _ensure_test_database() -> None:
    import subprocess

    from pgserver._commands import POSTGRES_BIN_PATH

    uri = _server.get_uri("postgres")
    result = subprocess.run(
        [
            str(POSTGRES_BIN_PATH / "psql"),
            uri,
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{_TEST_DB}'",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.strip() != "1":
        _server.psql(f"CREATE DATABASE {_TEST_DB};")


_ensure_test_database()

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from xfox.db import engine as engine_module  # noqa: E402
from xfox.db.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_database():
    """Fresh engine + schema per test, on the test's own event loop.

    The shared data directory is also wiped so filesystem workspaces stay in
    sync with the reset database (account ids restart from 1).
    """
    import shutil

    shutil.rmtree("/tmp/xfox-test-data", ignore_errors=True)

    engine_module._engine = None
    engine_module._session_factory = None

    engine = engine_module.get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()
    engine_module._engine = None
    engine_module._session_factory = None


@pytest.fixture
async def db_session():
    """A plain session for repository-level tests."""
    factory = engine_module.get_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client():
    """API client with cookie persistence (login flows)."""
    from xfox.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client


@pytest.fixture
async def admin_client(client: AsyncClient) -> AsyncClient:
    """A client authenticated as a fresh admin user."""
    import uuid

    username = f"admin_{uuid.uuid4().hex[:8]}"
    password = "AdminPass123!"
    await client.post("/api/auth/setup", json={"username": username, "password": password})
    await client.post("/api/auth/login", json={"username": username, "password": password})
    return client


@pytest.fixture
async def viewer_client(admin_client: AsyncClient) -> AsyncClient:
    """A viewer-role client on the same app as the admin fixture."""
    import uuid

    username = f"viewer_{uuid.uuid4().hex[:8]}"
    password = "ViewerPass123!"
    await admin_client.post(
        "/api/users", json={"username": username, "password": password, "role": "viewer"}
    )
    # Reuse the admin's client object but swap the session cookie to the viewer.
    await admin_client.post("/api/auth/logout")
    await admin_client.post("/api/auth/login", json={"username": username, "password": password})
    return admin_client
