# Tech Stack

## Backend
- Runtime: Node.js (CommonJS modules)
- Framework: Express 5
- Database: PostgreSQL 16 via `pg` (Pool)
- Auth: `jsonwebtoken` + `bcryptjs` (installed, not yet implemented)
- Validation: `joi`
- Security: `helmet`, `cors`
- Testing: Jest + Supertest

## Frontend
- Framework: React 19 (JSX, ES modules)
- Build tool: Vite 8
- Styling: Tailwind CSS 4
- Routing: React Router v7
- Data fetching: TanStack Query v5 + Axios
- Drag and drop: @dnd-kit/core + @dnd-kit/sortable
- Linting: ESLint 9

## Infrastructure
- Containerization: Docker + Docker Compose
- Reverse proxy: Nginx (routes `/api/*` to backend, serves frontend static files)
- Database service: `db` (postgres:16-alpine)
- API service: `api` (port 3000)
- Nginx service: port 80

## Common Commands

### Backend
```bash
cd backend
npm run dev       # nodemon dev server
npm start         # production server
npm test          # Jest (--passWithNoTests --forceExit)
```

### Frontend
```bash
cd frontend
npm run dev       # Vite dev server
npm run build     # production build
npm run lint      # ESLint
npm run preview   # preview production build
```

### Docker
```bash
docker-compose up --build    # start all services
docker-compose down          # stop all services
```
