import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin import setup_admin
from app.core.config import settings
from app.core.env_file import ensure_secret_keys
from app.core.error_handlers import init_exception_handlers
from app.database import dispose_engine
from app.middlewares import init_middlewares
from app.routes import router as api_router
from app.setup import init_setup

logging.basicConfig(level=logging.INFO if settings.DEBUG else logging.WARNING)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.DATABASE_URL:
        logger.warning(
            "No database configured. Open http://%s:%s/setup to set one up.", settings.HOST, settings.PORT
        )
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    # Outside production, generate SECRET_KEY / ENCRYPTION_KEY into .env if they're missing,
    # so a fresh clone starts without manual configuration.
    ensure_secret_keys()

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
        lifespan=lifespan,
    )

    init_exception_handlers(app)
    init_middlewares(app)
    init_setup(app)  # /setup wizard + redirect while no database is configured
    app.include_router(api_router)
    setup_admin(app)

    @app.get("/", tags=["Health Check"])
    async def health_check():
        return {"status": "ok", "message": "API is running successfully"}

    return app


app = create_app()
