from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.exceptions import register_error_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import engine
    from app.redis import redis_pool

    yield

    await engine.dispose()
    await redis_pool.aclose()


app = FastAPI(
    title=settings.app_name,
    description="AI-powered Indian Railways vacant seat finder",
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(app)

# Register routers
from app.modules.auth import router as auth_router
from app.modules.users import router as users_router
from app.modules.stations import router as stations_router
from app.modules.trains import router as trains_router
from app.modules.vacancy import router as vacancy_router
from app.modules.charts import router as charts_router
from app.modules.bookings import router as bookings_router
from app.modules.pnr import router as pnr_router
from app.modules.ai import router as ai_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(stations_router, prefix="/api/v1")
app.include_router(trains_router, prefix="/api/v1")
app.include_router(vacancy_router, prefix="/api/v1")
app.include_router(charts_router, prefix="/api/v1")
app.include_router(bookings_router, prefix="/api/v1")
app.include_router(pnr_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}
