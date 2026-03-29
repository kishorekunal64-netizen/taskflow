"""
Shared pytest fixtures for the FinIntelligence Platform Layer test suite.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Test secret (never a real secret) ────────────────────────────────────────
TEST_JWT_SECRET = "test-secret-do-not-use-in-production"
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "finintelligence_test")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "postgres")


# ── JWT token factories ───────────────────────────────────────────────────────

def _make_token(role: str, user_id: str | None = None) -> str:
    payload = {
        "user_id": user_id or str(uuid.uuid4()),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def admin_token() -> str:
    return _make_token("admin")


@pytest.fixture
def analyst_token() -> str:
    return _make_token("analyst")


@pytest.fixture
def viewer_token() -> str:
    return _make_token("viewer")


@pytest.fixture
def mock_conn():
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []
    return mock_conn, mock_cur


# ── App fixture — mocks DB pool and engine so no real infra needed ────────────

@pytest.fixture
def test_app():
    """
    Creates a FastAPI app instance with:
    - DB pool initialisation mocked (no real PostgreSQL required)
    - start_engine mocked (no APScheduler / finintelligence package required)
    - prewarm_cache mocked (no DB reads on startup)
    """
    import sys
    from unittest.mock import MagicMock

    # Stub out finintelligence so engine_bridge can be imported
    fini_stub = MagicMock()
    sys.modules.setdefault("finintelligence", fini_stub)
    sys.modules.setdefault("finintelligence.scheduler", fini_stub)
    sys.modules.setdefault("finintelligence.cache_manager", fini_stub)

    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []

    import finplatform.engine_bridge  # ensure module is loaded before patching

    with (
        patch("finplatform.db._pool", mock_pool),
        patch("finplatform.db.init_pool", return_value=None),
        patch("finplatform.db.close_pool", return_value=None),
        patch("finplatform.db.get_conn", return_value=mock_conn),
        patch("finplatform.durable_store.prewarm_cache", return_value=None),
        patch("finplatform.engine_bridge.start_engine", return_value=None),
    ):
        from finplatform.app import create_app
        app = create_app()
        yield app


@pytest_asyncio.fixture
async def async_client(test_app):
    """httpx AsyncClient wired to the test FastAPI app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ── DB fixture — isolated schema, rolled back after each test ─────────────────

@pytest.fixture
def test_db():
    """
    Provides a real psycopg2 connection to the test database.
    Wraps each test in a transaction that is rolled back on teardown,
    keeping tests isolated without truncating tables.

    Requires TEST_DB_* env vars or falls back to the defaults set above.
    Skips automatically if the test database is not reachable.
    """
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=3,
        )
    except Exception as exc:
        pytest.skip(f"Test database not reachable: {exc}")
        return

    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
