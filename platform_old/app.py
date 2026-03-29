from contextlib import asynccontextmanager
from fastapi import FastAPI
from platform.db import init_pool, close_pool
from platform.result_cache import cache
from platform.durable_store import prewarm_cache
from platform.engine_bridge import start_engine
from platform.middleware.jwt_auth import JWTMiddleware
from platform.routers import auth, dashboard, admin, analysis


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
    return app


app = create_app()
