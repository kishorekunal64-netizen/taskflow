# TaskFlow SaaS

TaskFlow is a task management SaaS application with a sprint board interface. It allows users to create, view, update, and delete tasks with priority levels and due dates.

## Core Domain

- Tasks are the primary entity: `id`, `title`, `done`, `priority` (low/medium/high), `due_date`, `created_at`
- The UI presents tasks as a sprint board
- The backend exposes a REST API consumed by the frontend

## Current State

The app is in early development. The frontend is a minimal React shell and the backend provides basic CRUD for tasks. Auth (JWT/bcrypt) is installed but not yet implemented.
