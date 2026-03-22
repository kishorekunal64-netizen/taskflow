# Project Structure

```
taskflow/
├── backend/                  # Node.js/Express API
│   ├── server.js             # Entry point, all routes defined here
│   ├── tests/
│   │   └── tasks.test.js     # Jest + Supertest integration tests
│   ├── .env                  # DB connection vars (not committed)
│   └── package.json
│
├── frontend/                 # React/Vite SPA
│   ├── src/
│   │   ├── main.jsx          # React root mount
│   │   ├── App.jsx           # Root component
│   │   ├── App.css
│   │   └── index.css         # Tailwind base styles
│   ├── public/               # Static assets (favicon, icons)
│   └── package.json
│
├── nginx/
│   └── nginx.conf            # Reverse proxy config
│
├── docker-compose.yml        # Orchestrates db, api, nginx services
└── .kiro/steering/           # AI steering rules
```

## Conventions

- Backend routes all live in `server.js` for now; prefix all API routes with `/api/`
- Frontend API calls go to `/api/` (relative, proxied by Nginx in production; full URL in dev)
- Backend uses CommonJS (`require`/`module.exports`); frontend uses ES modules (`import`/`export`)
- Environment config via `.env` in `backend/`; accessed through `process.env`
- DB access uses a single shared `pg.Pool` instance defined in `server.js`
- Tests live in `backend/tests/` and use Supertest against the exported `app`
