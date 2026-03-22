# Implementation Plan: create-task

## Overview

Add a validated `POST /api/tasks` endpoint to `backend/server.js` using `joi`, backed by the existing `pg.Pool`. Add Jest + Supertest example tests and fast-check property-based tests to `backend/tests/tasks.test.js`.

## Tasks

- [x] 1. Add joi validation schema to server.js
  - Define `createTaskSchema` using `joi` with `title` (required), `priority` (enum low/medium/high, default "medium"), and `due_date` (ISO date or null, default null)
  - Place the schema near the top of `server.js`, after the pool definition
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Replace the existing POST /api/tasks handler with a joi-validated version
  - [x] 2.1 Update the POST /api/tasks route handler in server.js
    - Run `createTaskSchema.validate(req.body, { abortEarly: true })` before any DB call
    - On validation error return `res.status(400).json({ error: error.details[0].message })`
    - On success run `INSERT INTO tasks (title, priority, due_date) VALUES ($1, $2, $3) RETURNING *` and return `res.status(201).json(result.rows[0])`
    - Keep the existing `try/catch` for DB errors returning 500
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

- [x] 3. Install fast-check dev dependency
  - Run `npm install --save-dev fast-check` inside `backend/`
  - _Requirements: 4 (enables property-based tests)_

- [x] 4. Add example tests and property-based tests to backend/tests/tasks.test.js
  - [x] 4.1 Add missing example test: invalid priority returns 400
    - POST `{ title: "x", priority: "urgent" }`, assert 400 and `error === "priority must be low, medium, or high"`
    - _Requirements: 4.3_

  - [x] 4.2 Write property test for Property 1: valid task creation round-trip
    - **Property 1: valid task creation round-trip**
    - Use `fc.record({ title: fc.string({ minLength: 1 }), priority: fc.constantFrom('low','medium','high') })`
    - Assert status 201, `res.body.title === title`, `res.body.id` defined, `res.body.created_at` defined
    - Tag comment: `// Feature: create-task, Property 1: valid task creation round-trip`
    - **Validates: Requirements 1.1, 3.1, 3.2**

  - [x] 4.3 Write property test for Property 2: default field values
    - **Property 2: default field values**
    - Use `fc.string({ minLength: 1 })` for title, omit priority and due_date
    - Assert status 201, `res.body.priority === 'medium'`, `res.body.due_date === null`
    - Tag comment: `// Feature: create-task, Property 2: default field values`
    - **Validates: Requirements 1.2, 1.3**

  - [x] 4.4 Write property test for Property 3: missing title rejected without DB write
    - **Property 3: missing title rejected without DB write**
    - Use `fc.record({ priority: fc.constantFrom('low','medium','high') })` (no title)
    - Assert status 400, `error === 'title is required'`, and task count unchanged
    - Tag comment: `// Feature: create-task, Property 3: missing title rejected without DB write`
    - **Validates: Requirements 2.1, 2.3**

  - [x] 4.5 Write property test for Property 4: invalid priority rejected without DB write
    - **Property 4: invalid priority rejected without DB write**
    - Use `fc.tuple(fc.string({ minLength: 1 }), fc.string({ minLength: 1 }).filter(s => !['low','medium','high'].includes(s)))`
    - Assert status 400, `error === 'priority must be low, medium, or high'`, and task count unchanged
    - Tag comment: `// Feature: create-task, Property 4: invalid priority rejected without DB write`
    - **Validates: Requirements 2.2, 2.3**

- [x] 5. Checkpoint — Ensure all tests pass
  - Run `npm test` in `backend/` and confirm all tests pass. Ask the user if any questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests require fast-check (task 3) to be installed first
- All routes stay in `server.js` per project convention
- The existing `pool` instance is reused — no new DB setup needed
