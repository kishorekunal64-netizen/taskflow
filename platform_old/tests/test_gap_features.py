"""
Tests for SOP gap features:
  - POST /auth/logout
  - GET /admin/activity
  - POST /analysis/run
  - Cache adapter (memory + redis no-op)
  - Alert manager thresholds
"""

import os
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "finintelligence_test")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "postgres")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_conn():
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, mock_cur


@pytest.fixture
def app(mock_conn):
    conn, _ = mock_conn
    with (
        patch("platform.db.init_pool"),
        patch("platform.db.close_pool"),
        patch("platform.db.get_conn", return_value=conn),
        patch("platform.durable_store.prewarm_cache"),
        patch("platform.engine_bridge.start_engine"),
    ):
        from platform.app import create_app
        return create_app()


@pytest_asyncio.fixture
async def client(app):
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _token(role: str) -> str:
    import jwt
    from datetime import datetime, timezone, timedelta
    import uuid
    payload = {
        "user_id": str(uuid.uuid4()),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, "test-secret-do-not-use-in-production", algorithm="HS256")


# ── Logout tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_returns_200_with_valid_token(client):
    resp = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {_token('viewer')}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logout successful"


@pytest.mark.asyncio
async def test_logout_requires_jwt(client):
    resp = await client.post("/auth/logout")
    assert resp.status_code == 401


# ── Admin activity tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_activity_returns_logs(client, mock_conn):
    _, mock_cur = mock_conn
    mock_cur.fetchall.return_value = [
        {"user_id": "abc", "action": "login", "timestamp": "2024-01-01T00:00:00", "ip_address": "1.2.3.4"}
    ]
    resp = await client.get(
        "/admin/activity",
        headers={"Authorization": f"Bearer {_token('admin')}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "logs" in body


@pytest.mark.asyncio
async def test_admin_activity_forbidden_for_viewer(client):
    resp = await client.get(
        "/admin/activity",
        headers={"Authorization": f"Bearer {_token('viewer')}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_activity_forbidden_for_analyst(client):
    resp = await client.get(
        "/admin/activity",
        headers={"Authorization": f"Bearer {_token('analyst')}"},
    )
    assert resp.status_code == 403


# ── Analysis trigger tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analysis_run_queued_for_admin(client):
    resp = await client.post(
        "/analysis/run",
        headers={"Authorization": f"Bearer {_token('admin')}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis_triggered"] is True
    assert body["status"] == "queued"
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_analysis_run_queued_for_analyst(client):
    resp = await client.post(
        "/analysis/run",
        headers={"Authorization": f"Bearer {_token('analyst')}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_analysis_run_forbidden_for_viewer(client):
    resp = await client.post(
        "/analysis/run",
        headers={"Authorization": f"Bearer {_token('viewer')}"},
    )
    assert resp.status_code == 403


# ── Cache adapter tests ───────────────────────────────────────────────────────

def test_memory_cache_set_get():
    from platform.cache.memory_cache import MemoryCache
    c = MemoryCache()
    c.set("k", {"v": 1})
    assert c.get("k") == {"v": 1}


def test_memory_cache_exists():
    from platform.cache.memory_cache import MemoryCache
    c = MemoryCache()
    assert not c.exists("missing")
    c.set("present", 42)
    assert c.exists("present")


def test_memory_cache_get_missing_returns_none():
    from platform.cache.memory_cache import MemoryCache
    c = MemoryCache()
    assert c.get("nope") is None


def test_redis_cache_noop_when_unavailable():
    """RedisCache must not raise even when Redis is not running."""
    from platform.cache.redis_cache import RedisCache
    c = RedisCache()  # will fail to connect silently
    c.set("k", "v")   # no-op
    assert c.get("k") is None
    assert c.exists("k") is False


def test_cache_manager_returns_memory_by_default():
    os.environ.pop("CACHE_BACKEND", None)
    from platform.cache import cache_manager
    import importlib
    importlib.reload(cache_manager)
    from platform.cache.cache_manager import get_cache
    from platform.cache.memory_cache import MemoryCache
    assert isinstance(get_cache(), MemoryCache)


# ── Alert manager tests ───────────────────────────────────────────────────────

def test_alert_manager_records_without_raising():
    from platform.monitoring.alert_manager import record, reset
    reset()
    for _ in range(3):
        record("api_errors")
    counts = __import__("platform.monitoring.alert_manager", fromlist=["get_counts"]).get_counts()
    assert counts.get("api_errors", 0) == 3


def test_alert_manager_unknown_metric_does_not_raise():
    from platform.monitoring.alert_manager import record
    record("nonexistent_metric")  # should just log warning, not raise


def test_alert_manager_reset_clears_counts():
    from platform.monitoring.alert_manager import record, reset, get_counts
    reset()
    record("scheduler_failures")
    reset()
    assert get_counts().get("scheduler_failures", 0) == 0
