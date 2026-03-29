# Design Document: FinIntelligence Platform Layer

## Overview

The FinIntelligence Platform Layer is a FastAPI application that wraps the existing `finintelligence/` engine package. It adds multi-user authentication (bcrypt + JWT), role-based access control, a shared in-memory Result_Cache, a PostgreSQL Durable_Store for cache pre-warming, a dashboard API, and admin user management — all without modifying the engine.

The engine's APScheduler jobs run in a background thread inside the same process. When a job completes, it writes results to both the in-memory Result_Cache and the PostgreSQL Durable_Store. The Dashboard_API reads exclusively from the in-memory cache; no engine code is ever called per user request.

---

## Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Process                          │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │  routers/    │   │  middleware/ │   │  result_cache.py │   │
│  │  auth.py     │   │  jwt_auth.py │   │  (threading.Lock)│   │
│  │  dashboard.py│   └──────────────┘   └────────┬─────────┘   │
│  │  admin.py    │                               │             │
│  └──────┬───────┘                               │             │
│         │                                       │             │
│  ┌──────▼───────────────────────────────────────▼──────────┐  │
│  │                    app.py (FastAPI)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          Engine Background Thread (APScheduler)          │  │
│  │  finintelligence/scheduler.py → jobs write to:           │  │
│  │    1. result_cache (in-memory)                           │  │
│  │    2. durable_store.py → PostgreSQL                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  PostgreSQL (User_DB)          Parquet/DuckDB (/data/)
  ├── users                     └── raw OHLCV candles
  ├── user_activity                  (engine-owned, unchanged)
  ├── analysis_results
  ├── sector_performance
  └── institutional_flow
```

### Request Flow

```
Client → JWT Middleware → Role Check → Route Handler → Result_Cache → JSON Response
                                                              ↑
                                              Engine Scheduler (background)
                                              writes on schedule only
```

### Startup Sequence

```
1. app.py lifespan starts
2. db.py creates connection pool
3. durable_store.py reads latest rows → populates Result_Cache
4. Engine APScheduler starts in background thread
5. FastAPI begins accepting requests
```

---

## Project Structure

```
platform/
├── app.py                    # FastAPI app factory, lifespan handler
├── db.py                     # psycopg2 connection pool
├── result_cache.py           # Thread-safe in-memory cache
├── durable_store.py          # PostgreSQL read/write for engine results
├── models.py                 # Pydantic v2 request/response models
├── routers/
│   ├── auth.py               # POST /auth/login
│   ├── dashboard.py          # GET /api/dashboard
│   └── admin.py              # /admin/users CRUD
├── middleware/
│   └── jwt_auth.py           # JWT validation middleware
├── engine_bridge.py          # Callbacks injected into engine scheduler jobs
├── schema.sql                # All 5 PostgreSQL table definitions
└── tests/
    ├── conftest.py           # pytest fixtures, test DB setup
    ├── test_auth.py
    ├── test_dashboard.py
    ├── test_admin.py
    └── test_result_cache.py
```

---

## Database Schema

All 5 tables live in the same PostgreSQL database. The schema is applied via `schema.sql` on first run.

```sql
-- schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── User accounts ──────────────────────────────────────────────────────────
CREATE TYPE user_role   AS ENUM ('admin', 'analyst', 'viewer');
CREATE TYPE user_status AS ENUM ('active', 'locked');

CREATE TABLE IF NOT EXISTS users (
    user_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT         NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    role          user_role    NOT NULL,
    status        user_status  NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);

-- ── Activity log ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_activity (
    id          BIGSERIAL    PRIMARY KEY,
    user_id     UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action      TEXT         NOT NULL,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ip_address  TEXT         NOT NULL
);

-- ── Durable result store ───────────────────────────────────────────────────
-- Stores computed engine outputs only. Raw OHLCV data stays in Parquet/DuckDB.

CREATE TABLE IF NOT EXISTS analysis_results (
    date              TIMESTAMPTZ  PRIMARY KEY,
    market_sentiment  JSONB,       -- serialised SentimentResult
    sector_strength   JSONB,       -- serialised list[SectorMetrics]
    ai_signal         JSONB        -- serialised OutlookSignal
);

CREATE TABLE IF NOT EXISTS sector_performance (
    date              TIMESTAMPTZ  NOT NULL,
    sector            TEXT         NOT NULL,
    momentum_score    FLOAT,
    relative_strength FLOAT,
    ranking           INT,
    PRIMARY KEY (date, sector)
);

CREATE TABLE IF NOT EXISTS institutional_flow (
    date      TIMESTAMPTZ  PRIMARY KEY,
    fii_buy   FLOAT,
    fii_sell  FLOAT,
    dii_buy   FLOAT,
    dii_sell  FLOAT,
    net_flow  FLOAT
);
```

---

## Components

### `app.py` — FastAPI Application Factory

Creates the FastAPI app, registers middleware, includes routers, and manages the lifespan (startup/shutdown).

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from platform.db import init_pool, close_pool
from platform.result_cache import cache
from platform.durable_store import prewarm_cache
from platform.engine_bridge import start_engine
from platform.middleware.jwt_auth import JWTMiddleware
from platform.routers import auth, dashboard, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    prewarm_cache(cache)          # read Durable_Store → populate Result_Cache
    start_engine(cache)           # start APScheduler in background thread
    yield
    close_pool()

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(JWTMiddleware)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    return app

app = create_app()
```

---

### `db.py` — PostgreSQL Connection Pool

Wraps a `psycopg2` `ThreadedConnectionPool`. All connection parameters come from environment variables.

```python
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import os

_pool: ThreadedConnectionPool | None = None

def init_pool() -> None:
    global _pool
    _pool = ThreadedConnectionPool(
        minconn=2, maxconn=10,
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

def get_conn():
    """Context manager: yields a connection, returns it to pool on exit."""
    ...

def close_pool() -> None:
    if _pool:
        _pool.closeall()
```

Environment variables required: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET`.

---

### `result_cache.py` — Thread-Safe In-Memory Cache

```python
import threading
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ResultCache:
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _data: dict[str, Any] = field(default_factory=lambda: {
        "market_sentiment": None,
        "sector_strength": None,
        "institutional_flows": None,
        "ai_signals": None,
    }, init=False)

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

cache = ResultCache()
```

The `cache` singleton is imported by `engine_bridge.py` (writes) and `routers/dashboard.py` (reads).

---

### `durable_store.py` — PostgreSQL Durable Result Store

Handles startup pre-warming and scheduler-triggered upserts. Never called from route handlers.

```python
def prewarm_cache(cache: ResultCache) -> None:
    """On startup: read latest row from each durable table, populate cache."""
    ...

def upsert_analysis_results(date, sentiment, sector_strength, ai_signal) -> None:
    """Called by engine_bridge after AI/sentiment cycle completes."""
    ...

def upsert_sector_performance(date, sector_metrics: list) -> None:
    """Called by engine_bridge after sector rotation cycle completes."""
    ...

def upsert_institutional_flow(date, flow) -> None:
    """Called by engine_bridge after institutional fetch cycle completes."""
    ...
```

All upserts use `INSERT ... ON CONFLICT DO UPDATE SET ...` so repeated writes are idempotent.

If any read during `prewarm_cache` fails, the error is logged and the affected cache key remains `null`.

---

### `engine_bridge.py` — Engine Integration

Injects write callbacks into the engine's scheduler jobs without modifying the engine package. Uses monkey-patching on the scheduler job functions after the scheduler is built.

```python
from finintelligence.scheduler import build_scheduler
from platform.result_cache import ResultCache
from platform import durable_store

def start_engine(cache: ResultCache) -> None:
    scheduler = build_scheduler()

    # Wrap each job to also write to Result_Cache and Durable_Store
    _wrap_sentiment_job(scheduler, cache)
    _wrap_sector_job(scheduler, cache)
    _wrap_institutional_job(scheduler, cache)
    _wrap_ai_signal_job(scheduler, cache)

    scheduler.start()
```

Each wrapper:
1. Calls the original job function
2. Reads the latest result from the engine's Cache_Manager
3. Writes to `result_cache` (in-memory)
4. Writes to `durable_store` (PostgreSQL)

This keeps the engine package unmodified.

---

### `middleware/jwt_auth.py` — JWT Validation Middleware

Starlette `BaseHTTPMiddleware` that validates the `Authorization: Bearer <token>` header on every request except `POST /auth/login`.

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import jwt, os

EXEMPT_PATHS = {("/auth/login", "POST")}

class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (request.url.path, request.method) in EXEMPT_PATHS:
            return await call_next(request)

        token = _extract_bearer(request)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        try:
            payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
            request.state.user_id = payload["user_id"]
            request.state.role    = payload["role"]
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        return await call_next(request)
```

---

### `routers/auth.py` — Login Endpoint

```
POST /auth/login
  Body: { email: str, password: str }
  Returns: { access_token: str, token_type: "bearer" }
```

Logic:
1. Look up user by email in `users` table
2. If not found or `status = locked` → HTTP 401 / 423
3. Verify password with `passlib.hash.bcrypt.verify()`
4. On failure: increment in-memory attempt counter (keyed by email, 15-min TTL); if count reaches 5, set `status = locked` in DB → HTTP 423
5. On success: reset attempt counter, update `last_login`, write `login` to `user_activity`, issue JWT
6. JWT payload: `{ user_id, role, exp: now + 24h }`, signed with `JWT_SECRET` via `PyJWT`

Failed login attempt counter is an in-memory `dict[email, (count, window_start)]` protected by a `threading.Lock`. It does not persist across restarts (acceptable — window resets on restart).

---

### `routers/dashboard.py` — Dashboard Endpoint

```
GET /api/dashboard
  Auth: Bearer JWT (any role)
  Returns: { market_sentiment, sector_strength, institutional_flows, ai_signals }
```

Logic:
1. JWT already validated by middleware; `request.state.role` is available
2. Call `cache.snapshot()` — single lock acquisition, O(1)
3. Write `dashboard_access` to `user_activity` (non-blocking: fire-and-forget thread)
4. Return snapshot as JSON; unpopulated keys are `null`

Response time target: < 500 ms (all in-memory, no I/O on the hot path).

---

### `routers/admin.py` — User Management Endpoints

```
POST   /admin/users          → create user (admin only)
GET    /admin/users          → list all users (admin only)
PATCH  /admin/users/{id}     → update user fields (admin only)
DELETE /admin/users/{id}     → delete user (admin only)
```

Role enforcement via a `require_role("admin")` dependency:

```python
from fastapi import Depends, HTTPException, Request

def require_role(*roles: str):
    def _check(request: Request):
        if request.state.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    return Depends(_check)
```

All endpoints use this dependency. JWT validation has already run in middleware, so a 403 here is always post-authentication.

All request bodies are validated by Pydantic v2 models (see `models.py`). `password_hash` is excluded from all responses.

---

### `models.py` — Pydantic v2 Request/Response Models

```python
from pydantic import BaseModel, EmailStr, UUID4
from typing import Literal, Optional
from datetime import datetime

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    user_id: UUID4
    email: EmailStr
    role: Literal["admin", "analyst", "viewer"]
    status: Literal["active", "locked"]
    created_at: datetime
    last_login: Optional[datetime]

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: Literal["admin", "analyst", "viewer"]

class UpdateUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[Literal["admin", "analyst", "viewer"]] = None
    status: Optional[Literal["active", "locked"]] = None

class DashboardResponse(BaseModel):
    market_sentiment: Optional[dict]
    sector_strength: Optional[list]
    institutional_flows: Optional[dict]
    ai_signals: Optional[dict]
```

Engine result types (`SentimentResult`, `SectorMetrics`, `OutlookSignal`, `InstitutionalFlow`) are serialised to `dict` via `dataclasses.asdict()` before being stored in the cache and returned in the dashboard response.

---

## Auth Flow

```
POST /auth/login
        │
        ▼
  Lookup user by email
        │
   ┌────┴────┐
   │ locked? │──yes──► HTTP 423
   └────┬────┘
        │ no
   ┌────▼────────────────┐
   │ bcrypt.verify(pw)   │
   └────┬────────────────┘
        │
   ┌────┴────┐
   │ match?  │──no──► increment attempt counter
   └────┬────┘              │
        │ yes          count == 5?──yes──► set status=locked, HTTP 423
        │                   │ no
        │              HTTP 401
        ▼
  reset counter
  update last_login
  write activity log (login)
  issue JWT (HS256, 24h)
        │
        ▼
  HTTP 200 { access_token, token_type }
```

---

## RBAC Enforcement Order

```
Request arrives
    │
    ▼
JWTMiddleware.dispatch()
    ├── exempt path? → pass through
    ├── no token?    → HTTP 401
    ├── bad token?   → HTTP 401
    └── valid token  → set request.state.{user_id, role}
                            │
                            ▼
                    Route handler
                            │
                    require_role() dependency
                            ├── role matches? → proceed
                            └── role mismatch → HTTP 403
```

HTTP 401 always comes from middleware (pre-route). HTTP 403 always comes from the `require_role` dependency (post-authentication). This satisfies Requirement 4.5.

---

## Engine Integration Detail

The engine's `scheduler.py` exposes `build_scheduler() -> BackgroundScheduler`. The platform wraps each job without touching the engine source:

```python
# engine_bridge.py (simplified)

def _wrap_sentiment_job(scheduler, cache):
    original = scheduler._lookup_job("sector_sentiment_job").func

    def wrapped():
        original()
        # read latest result from engine's cache_manager
        result = engine_cache_manager.read_latest_sentiment()
        if result:
            cache.set("market_sentiment", dataclasses.asdict(result))
            durable_store.upsert_analysis_results(...)

    scheduler.modify_job("sector_sentiment_job", func=wrapped)
```

The same pattern applies to the AI signal job, sector rotation job, and institutional flow job. All writes to `result_cache` and `durable_store` happen inside the scheduler's background thread — never on the request path.

---

## Durable Store Pre-Warming

On startup, `prewarm_cache()` runs before the scheduler starts and before the server accepts requests:

```python
def prewarm_cache(cache: ResultCache) -> None:
    try:
        row = _fetch_latest_analysis_results()
        if row:
            cache.set("market_sentiment", row["market_sentiment"])
            cache.set("sector_strength",  row["sector_strength"])
            cache.set("ai_signals",       row["ai_signal"])
    except Exception as e:
        logger.error(f"prewarm analysis_results failed: {e}")

    try:
        flow = _fetch_latest_institutional_flow()
        if flow:
            cache.set("institutional_flows", flow)
    except Exception as e:
        logger.error(f"prewarm institutional_flow failed: {e}")
```

If pre-warming fails for any key, that key stays `null` and the dashboard returns `null` for it until the next scheduler run populates it (Requirement 10.10).

---

## Cost Constraint Enforcement

| Constraint | Enforcement mechanism |
|---|---|
| Dashboard never calls engine | `routers/dashboard.py` only calls `cache.snapshot()` — no engine imports |
| Engine runs only on schedule | `engine_bridge.py` starts the scheduler; no route handler has a reference to it |
| No paid APIs | Platform layer has no HTTP client calls; all data comes from engine's existing free sources |
| Raw OHLCV stays in Parquet | `durable_store.py` only writes `SentimentResult`, `SectorMetrics`, `OutlookSignal`, and FII/DII summaries — no candle data |
| Durable_Store written by scheduler only | `upsert_*` functions in `durable_store.py` are called only from `engine_bridge.py` job wrappers |

---

## Correctness Properties

### Property 1: JWT Round-Trip

For any valid `(user_id, role)` pair, encoding a JWT with `PyJWT` and then decoding it with the same secret must produce the original `user_id` and `role` values unchanged.

**Validates: Requirements 1.1, 2.1, 2.4**

---

### Property 2: bcrypt Verification Consistency

For any plaintext password `p`, `bcrypt.hash(p)` followed by `bcrypt.verify(p, hash)` must return `True`, and `bcrypt.verify(q, hash)` for any `q ≠ p` must return `False`.

**Validates: Requirements 1.6, 7.1**

---

### Property 3: Result Cache Thread Safety

For any sequence of concurrent `set` and `get` operations on `ResultCache` from multiple threads, every `get` must return either the value set by the most recent `set` or a previously set value — it must never return a partially written value or raise an exception.

**Validates: Requirements 5.6**

---

### Property 4: Dashboard Response Completeness

For any snapshot of the Result_Cache, the dashboard response JSON must contain exactly the four keys `market_sentiment`, `sector_strength`, `institutional_flows`, `ai_signals`, each set to either a valid serialised object or `null` — no key may be absent and no extra keys may appear.

**Validates: Requirements 6.1, 6.2**

---

### Property 5: Role Enforcement Ordering

For any request with an invalid JWT, the response status code must be 401. For any request with a valid JWT but insufficient role, the response status code must be 403. The status code 403 must never be returned for a request that would have returned 401.

**Validates: Requirements 4.4, 4.5**

---

### Property 6: Login Attempt Counter Monotonicity

For any sequence of N consecutive failed login attempts for the same email within a 15-minute window, the attempt counter must reach exactly N after N attempts, and the account must be set to `locked` on exactly the 5th attempt — not before, not after.

**Validates: Requirements 1.2, 1.3**

---

### Property 7: Durable Store Upsert Idempotency

For any engine result object, calling `upsert_analysis_results` (or `upsert_sector_performance`, `upsert_institutional_flow`) twice with the same `date` key and the same data must produce exactly one row in the table — the second call must not create a duplicate row or raise an error.

**Validates: Requirements 10.4, 10.5, 10.6**

---

### Property 8: Pre-Warm Cache Consistency

For any state of the Durable_Store tables at startup, after `prewarm_cache()` completes, every Result_Cache key that has a corresponding non-null row in the Durable_Store must be populated with the deserialised value of that row's most recent entry.

**Validates: Requirements 10.7, 10.10**

---

### Property 9: Activity Log Non-Blocking

For any API request that triggers an activity log write, a simulated failure of the database write (e.g., connection error) must not cause the originating HTTP response to change its status code or body — the response must be identical to the success case.

**Validates: Requirements 8.5**

---

### Property 10: Password Hash Never Appears in Response

For any user management API response (POST /admin/users, GET /admin/users, PATCH /admin/users/{id}), the serialised JSON body must not contain a field named `password_hash` or any field whose value matches the bcrypt hash of the user's password.

**Validates: Requirements 7.1, 7.3, 7.4**

---

## Error Handling

| Scenario | Response |
|---|---|
| Missing/invalid JWT | HTTP 401 from middleware |
| Expired JWT | HTTP 401 from middleware |
| Insufficient role | HTTP 403 from `require_role` dependency |
| Login with wrong password | HTTP 401, generic message |
| Account locked | HTTP 423 |
| Duplicate email on create | HTTP 409 |
| User not found on PATCH/DELETE | HTTP 404 |
| Pydantic validation failure | HTTP 422 with field errors (FastAPI default) |
| Activity log write failure | Log error, do not fail request |
| Durable_Store read failure at startup | Log error, cache key stays null |
| DB connection failure on request | HTTP 500, logged |

---

## Testing Strategy

**Framework**: `pytest` + `httpx.AsyncClient` (via `httpx` transport for FastAPI) for integration tests. `unittest.mock` for mocking DB and engine calls.

**Property-based tests**: `hypothesis` for Properties 1–10 above.

### Test File Mapping

| File | Covers |
|---|---|
| `test_auth.py` | Login flow, lockout, JWT issuance, P2, P6 |
| `test_dashboard.py` | Cache reads, null keys, response shape, P4 |
| `test_admin.py` | CRUD, role enforcement, P5, P10 |
| `test_result_cache.py` | Thread safety, P3 |
| `conftest.py` | Test DB setup, fixtures for JWT tokens per role |

### Key Test Fixtures

```python
# conftest.py
@pytest.fixture
def admin_token() -> str: ...    # JWT with role=admin
@pytest.fixture
def analyst_token() -> str: ...  # JWT with role=analyst
@pytest.fixture
def viewer_token() -> str: ...   # JWT with role=viewer
@pytest.fixture
def test_db(): ...               # isolated test schema, rolled back after each test
```

Run tests with:
```bash
cd platform
pytest tests/ -v
```
