# Requirements Document

## Introduction

This feature adds a validated task creation endpoint to the TaskFlow API. Users can submit a new task with a title, priority, and optional due date via `POST /api/tasks`. The endpoint validates input, persists the task to PostgreSQL, and returns the created record. Invalid requests receive a structured 400 error response. Jest + Supertest tests cover the happy path and validation failures.

## Glossary

- **API**: The TaskFlow Express backend, running on Node.js, exposing routes under `/api/`
- **Task**: The primary domain entity with fields: `id`, `title`, `done`, `priority`, `due_date`, `created_at`
- **Priority**: An enumerated value — one of `low`, `medium`, or `high`
- **Validator**: The input validation logic applied to incoming request bodies before database writes
- **DB**: The PostgreSQL 16 database accessed via a shared `pg.Pool` instance

## Requirements

### Requirement 1: Accept Task Creation Request

**User Story:** As a user, I want to POST a new task with a title, priority, and due date, so that I can add tasks to my board.

#### Acceptance Criteria

1. WHEN a `POST /api/tasks` request is received with a valid body, THE API SHALL accept `title`, `priority`, and `due_date` fields from the request body.
2. WHEN `due_date` is omitted from the request body, THE API SHALL default `due_date` to `null`.
3. WHEN `priority` is omitted from the request body, THE API SHALL default `priority` to `medium`.

---

### Requirement 2: Validate Input

**User Story:** As a user, I want the API to reject invalid task data with a clear error, so that I know what to fix.

#### Acceptance Criteria

1. WHEN a `POST /api/tasks` request body does not include a `title` field, THE Validator SHALL return HTTP 400 with body `{ "error": "title is required" }`.
2. WHEN a `POST /api/tasks` request body includes a `priority` value that is not one of `low`, `medium`, or `high`, THE Validator SHALL return HTTP 400 with body `{ "error": "priority must be low, medium, or high" }`.
3. WHEN validation fails, THE API SHALL not write any data to the DB.

---

### Requirement 3: Persist Task to Database

**User Story:** As a user, I want created tasks to be saved, so that they persist across sessions.

#### Acceptance Criteria

1. WHEN a valid `POST /api/tasks` request is received, THE API SHALL insert a row into the `tasks` table with the provided `title`, `priority`, and `due_date`.
2. WHEN the DB insert succeeds, THE API SHALL return HTTP 201 with the full created task record, including the generated `id` and `created_at` timestamp.
3. IF the DB insert fails, THEN THE API SHALL return HTTP 500 with body `{ "error": "<error message>" }`.

---

### Requirement 4: Test Coverage

**User Story:** As a developer, I want Jest tests for task creation, so that regressions are caught automatically.

#### Acceptance Criteria

1. THE test suite SHALL include a test that sends a valid `POST /api/tasks` request and asserts HTTP 201, a defined `id`, and the correct `title` in the response body.
2. THE test suite SHALL include a test that sends a `POST /api/tasks` request without a `title` and asserts HTTP 400 with `{ "error": "title is required" }`.
3. THE test suite SHALL include a test that sends a `POST /api/tasks` request with an invalid `priority` and asserts HTTP 400 with `{ "error": "priority must be low, medium, or high" }`.
