# Requirements Document

## Introduction

The FinIntelligence Platform Layer is a multi-user web API that wraps the existing FinIntelligence market analysis engine. It adds user authentication, role-based access control, a shared result cache, a dashboard API, admin user management, and user activity logging — all without modifying the existing engine. The platform is built with FastAPI (Python) and PostgreSQL, keeping the entire stack in one language. The existing engine's AI analysis runs only on event triggers and its results are shared across all users via an in-memory result cache; the dashboard API reads from that cache exclusively and never triggers AI or data fetches.

## Glossary

- **Platform**: The FinIntelligence Platform Layer — the FastAPI web application defined in this document
- **Engine**: The existing FinIntelligence market analysis engine (finintelligence/ package) — not modified by this spec
- **Auth_Service**: The Platform component responsible for validating credentials, issuing JWT tokens, and enforcing login attempt limits
- **JWT**: JSON Web Token — a signed, time-limited bearer token issued by the Auth_Service on successful login
- **User_DB**: The PostgreSQL database storing user accounts, activity logs, and durable engine result tables
- **Result_Cache**: The in-memory Python dict (thread-safe) that stores the latest outputs from the Engine: market sentiment, sector strength, institutional flows, and AI signals
- **Durable_Store**: The three PostgreSQL tables (`analysis_results`, `sector_performance`, `institutional_flow`) that persist the latest Engine outputs so the Result_Cache can be pre-warmed on server restart
- **Dashboard_API**: The FastAPI route handler for `GET /api/dashboard` — reads from Result_Cache only
- **Admin_API**: The FastAPI route handlers under `/admin/users` — available to admin role only
- **Role**: One of three access levels assigned to each user: `admin`, `analyst`, or `viewer`
- **User**: A registered account in the User_DB with an email, password hash, role, and status
- **Activity_Log**: The PostgreSQL `user_activity` table recording login, logout, failed_login, and dashboard_access events
- **bcrypt**: The password hashing algorithm used via passlib; plain-text passwords are never stored or logged
- **Outlook_Signal**: The AI-generated market direction signal produced by the Engine's AI_Analysis_Engine and stored in the Result_Cache
- **SentimentResult**: The composite sentiment score and classification produced by the Engine's Sentiment_Engine and stored in the Result_Cache
- **SectorMetrics**: The sector rotation rankings produced by the Engine's Sector_Rotation_Engine and stored in the Result_Cache
- **InstitutionalFlow**: The FII/DII net flow data produced by the Engine's Institutional_Flow_Fetcher and stored in the Result_Cache

---

## Requirements

### Requirement 1: User Authentication — Login

**User Story:** As a registered user, I want to log in with my email and password, so that I can receive a JWT token and access the platform.

#### Acceptance Criteria

1. WHEN a POST request is received at `/auth/login` with a valid email and password matching a user record with status `active`, THE Auth_Service SHALL return a signed JWT token with a 24-hour expiry containing `user_id` and `role` claims
2. WHEN a POST request is received at `/auth/login` with a valid email but an incorrect password, THE Auth_Service SHALL increment the failed login attempt counter for that email and return HTTP 401 with a generic error message that does not reveal whether the email or password was incorrect
3. WHEN a POST request is received at `/auth/login` and the failed login attempt counter for that email reaches 5 within a 15-minute window, THE Auth_Service SHALL set the user account status to `locked` and return HTTP 423 with a message indicating the account is locked
4. WHILE a user account status is `locked`, THE Auth_Service SHALL reject all login attempts for that account with HTTP 423 until 15 minutes have elapsed since the fifth failed attempt, after which THE Auth_Service SHALL automatically restore the account status to `active`
5. IF a POST request is received at `/auth/login` with a missing or malformed request body, THEN THE Auth_Service SHALL return HTTP 422 with a field-level validation error
6. THE Auth_Service SHALL hash all password comparisons using bcrypt via passlib and SHALL never store, log, or transmit plain-text passwords

---

### Requirement 2: JWT Token Validation

**User Story:** As the platform, I want every protected API request to carry a valid JWT token, so that only authenticated users can access platform resources.

#### Acceptance Criteria

1. THE Platform SHALL validate the JWT signature, expiry, and presence of `user_id` and `role` claims on every request to any route except `POST /auth/login`
2. IF a request arrives without an `Authorization: Bearer <token>` header, THEN THE Platform SHALL return HTTP 401
3. IF a request arrives with a JWT token whose signature is invalid or whose expiry has passed, THEN THE Platform SHALL return HTTP 401
4. WHEN a JWT token is valid, THE Platform SHALL make the `user_id` and `role` claims available to the route handler for downstream access control decisions
5. THE Platform SHALL sign all issued JWT tokens using a secret key loaded from an environment variable and SHALL NOT use a hardcoded secret

---

### Requirement 3: User Database

**User Story:** As a system operator, I want user accounts stored in PostgreSQL, so that user data persists across platform restarts.

#### Acceptance Criteria

1. THE User_DB SHALL contain a `users` table with columns: `user_id` (UUID primary key), `email` (unique, not null), `password_hash` (text, not null), `role` (enum: `admin`, `analyst`, `viewer`, not null), `status` (enum: `active`, `locked`, not null, default `active`), `created_at` (timestamptz, not null, default now()), `last_login` (timestamptz, nullable)
2. WHEN a user successfully authenticates, THE User_DB SHALL update the `last_login` column for that user to the current UTC timestamp
3. THE User_DB SHALL enforce a unique constraint on the `email` column so that no two user records share the same email address
4. THE Platform SHALL connect to the User_DB using asyncpg or psycopg2 with connection parameters loaded exclusively from environment variables

---

### Requirement 4: Role-Based Access Control

**User Story:** As a system operator, I want each user role to have a defined set of permitted actions, so that access to sensitive operations is restricted by role.

#### Acceptance Criteria

1. WHEN a request is made by a user with role `admin`, THE Platform SHALL permit: all user management operations under `/admin/users`, viewing system activity logs, and all operations permitted to `analyst` and `viewer` roles
2. WHEN a request is made by a user with role `analyst`, THE Platform SHALL permit: reading dashboard data from `GET /api/dashboard` and all operations permitted to the `viewer` role
3. WHEN a request is made by a user with role `viewer`, THE Platform SHALL permit: reading market signals and sentiment data from `GET /api/dashboard`
4. IF a request is made to a route that requires a role the authenticated user does not hold, THEN THE Platform SHALL return HTTP 403 with a message indicating insufficient permissions
5. THE Platform SHALL enforce role checks after JWT validation — a request that fails JWT validation SHALL receive HTTP 401, not HTTP 403

---

### Requirement 5: Result Cache Layer

**User Story:** As the platform, I want a shared in-memory result cache that holds the latest Engine outputs, so that all users read the same pre-computed data without triggering AI or data fetches.

#### Acceptance Criteria

1. THE Result_Cache SHALL store the latest value for each of the following keys: `market_sentiment` (SentimentResult), `sector_strength` (list of SectorMetrics), `institutional_flows` (InstitutionalFlow), `ai_signals` (OutlookSignal)
2. WHEN the Engine's AI_Analysis_Engine completes a trigger run, THE Result_Cache SHALL be updated with the new OutlookSignal before the run is considered complete
3. WHEN the Engine's Sentiment_Engine completes a computation cycle, THE Result_Cache SHALL be updated with the new SentimentResult
4. WHEN the Engine's Sector_Rotation_Engine completes a computation cycle, THE Result_Cache SHALL be updated with the new list of SectorMetrics
5. WHEN the Engine's Institutional_Flow_Fetcher completes a fetch cycle, THE Result_Cache SHALL be updated with the latest InstitutionalFlow record
6. THE Result_Cache SHALL be implemented as a thread-safe Python dict protected by a threading.Lock so that concurrent reads and writes do not produce inconsistent state
7. THE Dashboard_API SHALL read exclusively from the Result_Cache and SHALL NOT call any Engine component, trigger any data fetch, or invoke any AI analysis

---

### Requirement 6: Dashboard API

**User Story:** As an authenticated user, I want a single dashboard endpoint that returns the latest market intelligence, so that I can view current signals without waiting for computation.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/dashboard` with a valid JWT token from a user with role `admin`, `analyst`, or `viewer`, THE Dashboard_API SHALL return HTTP 200 with a JSON body containing: `market_sentiment`, `sector_strength`, `institutional_flows`, and `ai_signals` read from the Result_Cache
2. WHEN a GET request is received at `/api/dashboard` and one or more Result_Cache keys have not yet been populated (Engine has not completed its first run), THE Dashboard_API SHALL return HTTP 200 with the available keys populated and the unpopulated keys set to `null`
3. THE Dashboard_API SHALL return the response within 500 milliseconds of receiving the request, as all data is read from the in-memory Result_Cache with no I/O
4. IF a GET request is received at `/api/dashboard` without a valid JWT token, THEN THE Dashboard_API SHALL return HTTP 401
5. THE Dashboard_API SHALL log each successful access to the Activity_Log with `action` = `dashboard_access`, `user_id`, `timestamp`, and `ip_address`

---

### Requirement 7: Admin User Management API

**User Story:** As an admin, I want API endpoints to create, list, update, and delete user accounts, so that I can manage platform access without direct database access.

#### Acceptance Criteria

1. WHEN a POST request is received at `/admin/users` with a valid admin JWT and a body containing `email`, `password`, and `role`, THE Admin_API SHALL create a new user record in the User_DB with a bcrypt-hashed password and return HTTP 201 with the created user object excluding `password_hash`
2. IF a POST request is received at `/admin/users` and the provided email already exists in the User_DB, THEN THE Admin_API SHALL return HTTP 409 with an error indicating the email is already registered
3. WHEN a GET request is received at `/admin/users` with a valid admin JWT, THE Admin_API SHALL return HTTP 200 with a JSON array of all user records excluding `password_hash`
4. WHEN a PATCH request is received at `/admin/users/{id}` with a valid admin JWT and a body containing one or more of `email`, `role`, or `status`, THE Admin_API SHALL update the specified fields for the user with the given `user_id` and return HTTP 200 with the updated user object excluding `password_hash`
5. IF a PATCH request is received at `/admin/users/{id}` and no user with the given `user_id` exists, THEN THE Admin_API SHALL return HTTP 404
6. WHEN a DELETE request is received at `/admin/users/{id}` with a valid admin JWT, THE Admin_API SHALL remove the user record with the given `user_id` from the User_DB and return HTTP 204
7. IF a DELETE request is received at `/admin/users/{id}` and no user with the given `user_id` exists, THEN THE Admin_API SHALL return HTTP 404
8. IF any request is received at any `/admin/users` route with a valid JWT from a user whose role is not `admin`, THEN THE Admin_API SHALL return HTTP 403
9. THE Admin_API SHALL validate all request bodies using Pydantic models and SHALL return HTTP 422 with field-level errors for any missing or invalid fields

---

### Requirement 8: User Activity Logging

**User Story:** As an admin, I want all significant user actions recorded in the database, so that I can audit platform usage and investigate security incidents.

#### Acceptance Criteria

1. THE User_DB SHALL contain a `user_activity` table with columns: `id` (bigserial primary key), `user_id` (UUID, foreign key to `users.user_id`), `action` (text, not null), `timestamp` (timestamptz, not null, default now()), `ip_address` (text, not null)
2. WHEN a user successfully authenticates via `POST /auth/login`, THE Activity_Log SHALL record an entry with `action` = `login`, the authenticated `user_id`, the current UTC timestamp, and the client IP address
3. WHEN a login attempt fails due to an incorrect password, THE Activity_Log SHALL record an entry with `action` = `failed_login`, the `user_id` associated with the submitted email (if the email exists), the current UTC timestamp, and the client IP address
4. WHEN a user accesses `GET /api/dashboard` successfully, THE Activity_Log SHALL record an entry with `action` = `dashboard_access`, the authenticated `user_id`, the current UTC timestamp, and the client IP address
5. THE Activity_Log write operation SHALL be non-blocking with respect to the API response — a failure to write an activity log entry SHALL be logged to the application error log but SHALL NOT cause the originating API request to fail
6. THE Platform SHALL extract the client IP address from the `X-Forwarded-For` header when present, falling back to the direct connection remote address

---

### Requirement 9: Cost and Data Source Constraints

**User Story:** As a system operator, I want the platform to enforce strict cost controls, so that AI analysis and data fetching costs remain zero regardless of user traffic.

#### Acceptance Criteria

1. THE Dashboard_API SHALL read exclusively from the Result_Cache and SHALL NOT invoke any method on the Engine's AI_Analysis_Engine, Data_Fetcher, Institutional_Flow_Fetcher, News_Ingester, or Sentiment_Engine
2. THE Platform SHALL use only free, publicly accessible data sources inherited from the Engine: Yahoo Finance (via yfinance), NSE public datasets, NSDL public datasets, and RSS feeds
3. THE Result_Cache SHALL be populated exclusively by the Engine's scheduled trigger runs — no user request, admin action, or API call SHALL cause the Engine to run outside its APScheduler-defined schedule
4. THE Platform SHALL maintain the Engine's local Parquet/DuckDB cache under `/data/` as the sole persistent data store for raw OHLCV candle data — raw market OHLCV data SHALL NOT be stored in PostgreSQL
5. THE Durable_Store tables (`analysis_results`, `sector_performance`, `institutional_flow`) SHALL store only computed Engine results (SentimentResult, SectorMetrics, OutlookSignal, and FII/DII net flow summaries) and SHALL NOT store raw OHLCV candle data
6. WHEN the Engine's scheduler writes to the Durable_Store, THE Platform SHALL perform those writes exclusively from the Engine's scheduled job callbacks — no user request, admin action, or API call SHALL trigger a write to the Durable_Store

---

### Requirement 10: Durable Result Store (PostgreSQL)

**User Story:** As a system operator, I want the latest Engine outputs persisted in PostgreSQL, so that the in-memory Result_Cache can be pre-warmed on server restart without waiting for the next scheduled Engine run.

#### Acceptance Criteria

1. THE User_DB SHALL contain an `analysis_results` table with columns: `date` (timestamptz, primary key), `market_sentiment` (jsonb — serialised SentimentResult), `sector_strength` (jsonb — serialised list of SectorMetrics), `ai_signal` (jsonb — serialised OutlookSignal)
2. THE User_DB SHALL contain a `sector_performance` table with columns: `date` (timestamptz), `sector` (text), `momentum_score` (float), `relative_strength` (float), `ranking` (int), with a composite primary key of `(date, sector)`
3. THE User_DB SHALL contain an `institutional_flow` table with columns: `date` (timestamptz, primary key), `fii_buy` (float), `fii_sell` (float), `dii_buy` (float), `dii_sell` (float), `net_flow` (float)
4. WHEN the Engine's scheduler completes a computation cycle that produces new results, THE Platform SHALL upsert the latest SentimentResult, SectorMetrics list, and OutlookSignal into the `analysis_results` table using the result timestamp as the primary key
5. WHEN the Engine's scheduler completes a sector rotation cycle, THE Platform SHALL upsert each SectorMetrics record into the `sector_performance` table using `(date, sector)` as the composite key
6. WHEN the Engine's Institutional_Flow_Fetcher completes a fetch cycle, THE Platform SHALL upsert the latest FII/DII flow summary into the `institutional_flow` table using the trading date as the primary key
7. WHEN the Platform starts up, THE Platform SHALL read the most recent row from each Durable_Store table and populate the corresponding Result_Cache keys before accepting any API requests
8. THE Durable_Store tables SHALL be written exclusively by the Engine's scheduled job callbacks — no user request, admin action, or Dashboard_API call SHALL write to or modify any Durable_Store table
9. THE Dashboard_API SHALL continue to read exclusively from the in-memory Result_Cache and SHALL NOT query the Durable_Store tables directly at request time
10. IF a Durable_Store read fails during platform startup, THEN THE Platform SHALL log the error and start with the affected Result_Cache keys set to `null`, allowing the cache to be populated on the next scheduled Engine run

