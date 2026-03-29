from contextlib import asynccontextmanager
from fastapi import FastAPI
from finplatform.db import init_pool, close_pool
from finplatform.result_cache import cache
from finplatform.durable_store import prewarm_cache
from finplatform.engine_bridge import start_engine
from finplatform.middleware.jwt_auth import JWTMiddleware
from finplatform.routers import auth, dashboard, admin, analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    prewarm_cache(cache)
    start_engine(cache)
    yield
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="FinIntelligence Platform", lifespan=lifespan)
    app.add_middleware(JWTMiddleware)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(analysis.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.2"}

    return app


app = create_app()
