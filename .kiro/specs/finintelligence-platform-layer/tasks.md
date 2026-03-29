98# Implementation Plan: FinIntelligence Platform Layer

## Overview

Build a standalone FastAPI application at `platform/` that wraps the existing `finintelligence/` engine package. The implementation proceeds in strict dependency order: environment → models → DB pool → cache → durable store → middleware → routers → engine bridge → app factory → tests. No route handler ever imports the engine; all engine writes flow exclusively through `engine_bridge.py` job wrappers.

## Tasks

- [x] 1. Environment setup
  - Create `platform/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `psycopg2-binary`, `PyJWT`, `passlib[bcrypt]`, `pydantic[email]`, `httpx`, `pytest`, `hypothesis`, `pytest-asyncio`
  - Create `platform/__init__.py` (empty)
  - Create `platform/routers/__init__.py` (empty)
  - Create `platform/middleware/__init__.py` (empty)
  - Create `platform/tests/__init__.py` (empty)
  - Create `platform/schema.sql` with all 5 table definitions: `users` (UUID PK, email unique, password_hash, role enum, status enum, created_at, last_login), `user_activity` (bigserial PK, user_id FK, action, timestamp, ip_address), `analysis_results` (date PK, market_sentiment JSONB, sector_strength JSONB, ai_signal JSONB), `sector_performance` (date + sector composite PK, momentum_score, relative_strength, ranking), `institutional_flow` (date PK, fii_buy, fii_sell, dii_buy, dii_sell, net_flow)
  - Include `CREATE EXTENSION IF NOT EXISTS "pgcrypto"` and `CREATE TYPE` for `user_role` and `user_status` enums
  - _Requirements: 3.1, 8.1, 10.1, 10.2, 10.3_

- [x] 2. Pydantic v2 models
  - [x] 2.1 Create `platform/models.py` with all request/response models
    - `LoginRequest(email: EmailStr, password: str)`
    - `TokenResponse(access_token: str, token_type: str = "bearer")`
    - `UserResponse(user_id: UUID4, email: EmailStr, role: Literal["admin","analyst","viewer"], status: Literal["active","locked"], created_at: datetime, last_login: Optional[datetime])` — `password_hash` excluded via `model_config`
    - `CreateUserRequest(email: EmailStr, password: str, role: Literal["admin","analyst","viewer"])`
    - `UpdateUserRequest` with all fields Optional
    - `DashboardResponse(market_sentiment: Optional[dict], sector_strength: Optional[list], institutional_flows: Optional[dict], ai_signals: Optional[dict])`
    - _Requirements: 1.5, 7.1, 7.3, 7.4, 7.9_

  - [ ]* 2.2 Write property test for password hash exclusion (Property 10)
    - **Property 10: Password Hash Never Appears in Response**
    - **Validates: Requirements 7.1, 7.3, 7.4**
    - Use `hypothesis` to generate arbitrary email/password/role combos; assert `UserResponse` serialised JSON never contains `password_hash` key or a bcrypt-hash-shaped value

- [x] 3. PostgreSQL connection pool
  - [x] 3.1 Create `platform/db.py` with `ThreadedConnectionPool` (minconn=2, maxconn=10)
    - `init_pool()` reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` from `os.environ`
    - `get_conn()` as a context manager that calls `getconn()` on enter and `putconn()` on exit
    - `close_pool()` calls `_pool.closeall()`
    - All connection params loaded exclusively from environment variables — no hardcoded values
    - _Requirements: 3.4_

- [x] 4. Thread-safe result cache
  - [x] 4.1 Create `platform/result_cache.py` with `ResultCache` dataclass
    - Internal `threading.Lock` and `_data: dict` with four keys: `market_sentiment`, `sector_strength`, `institutional_flows`, `ai_signals` — all initialised to `None`
    - `get(key)`, `set(key, value)`, `snapshot()` — all acquire the lock
    - Module-level `cache = ResultCache()` singleton
    - _Requirements: 5.1, 5.6_

  - [ ]* 4.2 Write property test for Result Cache thread safety (Property 3)
    - **Property 3: Result Cache Thread Safety**
    - **Validates: Requirements 5.6**
    - Use `hypothesis` with `@given(st.lists(...))` to generate concurrent set/get sequences; run via `threading.Thread`; assert no exception raised and every `get` returns a valid (not partial) value

- [x] 5. Durable store
  - [x] 5.1 Create `platform/durable_store.py` with pre-warm and upsert functions
    - `prewarm_cache(cache: ResultCache)` — reads latest row from `analysis_results` and `institutional_flow`; populates cache keys; logs and continues on any read failure (cache key stays `None`)
    - `upsert_analysis_results(date, sentiment_dict, sector_strength_list, ai_signal_dict)` — `INSERT ... ON CONFLICT (date) DO UPDATE SET ...`
    - `upsert_sector_performance(date, sector_metrics_list)` — upserts each row with composite key `(date, sector)`
    - `upsert_institutional_flow(date, flow_dict)` — `INSERT ... ON CONFLICT (date) DO UPDATE SET ...`
    - All upserts called ONLY from `engine_bridge.py` — no imports of this module from any router
    - _Requirements: 10.4, 10.5, 10.6, 10.7, 10.10_

  - [x] 5.2 Write property test for durable store upsert idempotency (Property 7)
    - **Property 7: Durable Store Upsert Idempotency**
    - **Validates: Requirements 10.4, 10.5, 10.6**
    - Use `hypothesis` with a mock DB connection; call each upsert function twice with the same date key; assert exactly one row exists and no exception raised

  - [ ]* 5.3 Write property test for pre-warm cache consistency (Property 8)
    - **Property 8: Pre-Warm Cache Consistency**
    - **Validates: Requirements 10.7, 10.10**
    - Use `hypothesis` to generate arbitrary DB row states; assert that after `prewarm_cache()` every non-null DB row is reflected in the cache, and null DB rows leave cache key as `None`

- [x] 6. JWT middleware
  - [x] 6.1 Create `platform/middleware/jwt_auth.py` with `JWTMiddleware(BaseHTTPMiddleware)`
    - Exempt path: `("/auth/login", "POST")`
    - Extract `Authorization: Bearer <token>` header; return `JSONResponse(401)` if missing
    - Decode with `jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])`; return `JSONResponse(401)` on `PyJWTError`
    - On success: set `request.state.user_id` and `request.state.role`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 6.2 Write property test for JWT round-trip (Property 1)
    - **Property 1: JWT Round-Trip**
    - **Validates: Requirements 1.1, 2.1, 2.4**
    - Use `hypothesis` with `@given(st.uuids(), st.sampled_from(["admin","analyst","viewer"]))` to generate `(user_id, role)` pairs; encode then decode; assert decoded claims match originals

  - [ ]* 6.3 Write property test for role enforcement ordering (Property 5)
    - **Property 5: Role Enforcement Ordering**
    - **Validates: Requirements 4.4, 4.5**
    - Use `hypothesis` to generate invalid tokens and valid-but-wrong-role tokens; assert invalid token always yields 401 and valid-wrong-role always yields 403; assert 403 never returned for a request that would yield 401

- [x] 7. Auth router
  - [x] 7.1 Create `platform/routers/auth.py` with `POST /auth/login`
    - Look up user by email via `db.get_conn()`; return HTTP 401 if not found (generic message)
    - Return HTTP 423 if `status = locked`
    - Verify password with `passlib.hash.bcrypt.verify()`
    - On failure: increment in-memory attempt counter `dict[email, (count, window_start)]` protected by `threading.Lock`; if count reaches 5 within 15-min window, set `status = locked` in DB and return HTTP 423
    - On success: reset counter, update `last_login`, write `login` to `user_activity`, issue JWT `{user_id, role, exp: now+24h}` signed with `os.environ["JWT_SECRET"]`
    - Write `failed_login` to `user_activity` on password mismatch (non-blocking, fire-and-forget thread)
    - Extract client IP from `X-Forwarded-For` header, fallback to `request.client.host`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.2, 8.3, 8.6_

  - [ ]* 7.2 Write property test for bcrypt verification consistency (Property 2)
    - **Property 2: bcrypt Verification Consistency**
    - **Validates: Requirements 1.6, 7.1**
    - Use `hypothesis` with `@given(st.text(min_size=1))` for passwords; assert `bcrypt.verify(p, bcrypt.hash(p))` is always `True` and `bcrypt.verify(q, hash)` for `q != p` is always `False`

  - [ ]* 7.3 Write property test for login attempt counter monotonicity (Property 6)
    - **Property 6: Login Attempt Counter Monotonicity**
    - **Validates: Requirements 1.2, 1.3**
    - Use `hypothesis` with `@given(st.integers(min_value=1, max_value=10))` for attempt counts; assert counter reaches exactly N after N attempts; assert lockout triggered on exactly the 5th attempt

  - [ ]* 7.4 Write unit tests for auth router in `platform/tests/test_auth.py`
    - Test successful login returns 200 with `access_token`
    - Test wrong password returns 401 with generic message
    - Test locked account returns 423
    - Test 5th failed attempt locks account and returns 423
    - Test missing body returns 422
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 8. Checkpoint — auth layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Dashboard router
  - [x] 9.1 Create `platform/routers/dashboard.py` with `GET /api/dashboard`
    - Import ONLY `from platform.result_cache import cache` — no engine imports whatsoever
    - Call `cache.snapshot()` to get all four keys in a single lock acquisition
    - Write `dashboard_access` to `user_activity` in a fire-and-forget `threading.Thread` (failure must not affect response)
    - Extract client IP from `X-Forwarded-For` header, fallback to `request.client.host`
    - Return `DashboardResponse` — unpopulated keys serialise as `null`
    - _Requirements: 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 9.1_

  - [ ]* 9.2 Write property test for dashboard response completeness (Property 4)
    - **Property 4: Dashboard Response Completeness**
    - **Validates: Requirements 6.1, 6.2**
    - Use `hypothesis` to generate arbitrary cache states (any combination of None and dict values); assert response JSON always contains exactly the four keys and each is either a valid object or `null`

  - [ ]* 9.3 Write property test for activity log non-blocking (Property 9)
    - **Property 9: Activity Log Non-Blocking**
    - **Validates: Requirements 8.5**
    - Simulate DB write failure via mock; assert HTTP response status code and body are identical to the success case

  - [ ]* 9.4 Write unit tests for dashboard router in `platform/tests/test_dashboard.py`
    - Test all four keys present when cache is fully populated
    - Test null keys when cache is empty
    - Test 401 when no JWT provided
    - Test all three roles (admin, analyst, viewer) can access dashboard
    - _Requirements: 6.1, 6.2, 6.4_

- [x] 10. Admin router
  - [x] 10.1 Create `platform/routers/admin.py` with `/admin/users` CRUD
    - `require_role("admin")` FastAPI dependency on all four routes; reads `request.state.role`; raises `HTTPException(403)` on mismatch
    - `POST /admin/users` — hash password with `passlib.hash.bcrypt.hash()`, insert into `users`, return HTTP 201 `UserResponse`; return HTTP 409 on duplicate email
    - `GET /admin/users` — return HTTP 200 list of `UserResponse` (no `password_hash`)
    - `PATCH /admin/users/{id}` — update only provided fields; return HTTP 200 `UserResponse`; return HTTP 404 if not found
    - `DELETE /admin/users/{id}` — delete user; return HTTP 204; return HTTP 404 if not found
    - _Requirements: 4.1, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [ ]* 10.2 Write unit tests for admin router in `platform/tests/test_admin.py`
    - Test create user returns 201 with no `password_hash` in response
    - Test duplicate email returns 409
    - Test list users returns array with no `password_hash`
    - Test patch updates only specified fields
    - Test patch unknown user returns 404
    - Test delete returns 204
    - Test delete unknown user returns 404
    - Test non-admin JWT on all four routes returns 403
    - _Requirements: 7.1–7.9, 4.4, 4.5_

- [x] 11. Engine bridge
  - [x] 11.1 Create `platform/engine_bridge.py` with `start_engine(cache: ResultCache)`
    - Call `finintelligence.scheduler.build_scheduler()` to get the scheduler
    - Wrap `news_ingestion_job` (id: `news_ingestion`): after original runs, read `cache_manager.read_latest_signal()` and `cache_manager.read_sentiment()` equivalent; call `cache.set("market_sentiment", ...)` and `durable_store.upsert_analysis_results(...)`
    - Wrap `institutional_flow_job` (id: `institutional_flow`): after original runs, read latest institutional flows; call `cache.set("institutional_flows", ...)` and `durable_store.upsert_institutional_flow(...)`; also read sector metrics and call `cache.set("sector_strength", ...)` and `durable_store.upsert_sector_performance(...)`
    - Wrap `market_refresh` job: after original runs, read latest AI signal if available; call `cache.set("ai_signals", ...)`
    - Use `scheduler.modify_job(job_id, func=wrapped_fn)` for each wrap
    - Serialise engine dataclasses with `dataclasses.asdict()` before storing in cache or durable store
    - Call `scheduler.start()` — this is the ONLY place the scheduler is started
    - No router or route handler imports `engine_bridge`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 9.3, 9.6, 10.4, 10.5, 10.6_

- [x] 12. App factory
  - [x] 12.1 Create `platform/app.py` with `create_app()` and lifespan handler
    - `@asynccontextmanager async def lifespan(app)`: call `init_pool()`, `prewarm_cache(cache)`, `start_engine(cache)`, then `yield`, then `close_pool()`
    - `create_app()`: instantiate `FastAPI(lifespan=lifespan)`, add `JWTMiddleware`, include `auth.router`, `dashboard.router`, `admin.router`
    - Module-level `app = create_app()` for uvicorn entry point
    - _Requirements: 2.1, 3.4, 10.7_

- [x] 13. Test fixtures and conftest
  - [x] 13.1 Create `platform/tests/conftest.py` with shared pytest fixtures
    - `admin_token()` fixture — JWT with `role=admin`, signed with test secret
    - `analyst_token()` fixture — JWT with `role=analyst`
    - `viewer_token()` fixture — JWT with `role=viewer`
    - `test_app()` fixture — `create_app()` with mocked DB pool and mocked `start_engine`
    - `async_client(test_app)` fixture — `httpx.AsyncClient(app=test_app, base_url="http://test")`
    - `test_db` fixture — isolated schema using a test PostgreSQL connection, rolled back after each test
    - _Requirements: all test requirements_

  - [x] 13.2 Create `platform/tests/test_result_cache.py`
    - Test `get` returns `None` for uninitialised keys
    - Test `set` then `get` returns correct value
    - Test `snapshot` returns all four keys
    - Test concurrent `set`/`get` from 10 threads does not raise
    - _Requirements: 5.1, 5.6_

- [ ] 14. Final checkpoint — all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run: `cd platform && pytest tests/ -v`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Cost constraints are enforced structurally: `routers/dashboard.py` has zero engine imports; `durable_store.py` upserts are called only from `engine_bridge.py`; no raw OHLCV data is written to PostgreSQL
- All environment variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET`) must be present at runtime — no hardcoded fallbacks
- Property tests (Properties 1–10) map directly to design document correctness properties
- The scheduler is started exactly once, inside `engine_bridge.start_engine()`, called from the lifespan handler
