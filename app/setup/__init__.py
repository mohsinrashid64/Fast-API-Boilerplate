"""First-run setup: when no database is configured the app serves a wizard at /setup."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import settings
from app.core.env_file import refresh_if_env_changed
from app.database import init_engine
from app.setup.routes import router

ALWAYS_ALLOWED = ("/setup", "/admin/statics")


def init_setup(app: FastAPI) -> None:
    app.include_router(router)

    @app.middleware("http")
    async def setup_guard(request: Request, call_next):
        if not settings.is_configured:
            # Setup may have been completed by another worker process: pick up `.env` changes.
            if refresh_if_env_changed() and settings.is_configured:
                init_engine(settings.DATABASE_URL)

        if settings.is_configured or request.url.path.startswith(ALWAYS_ALLOWED):
            return await call_next(request)

        if not settings.setup_wizard_enabled:
            return JSONResponse(status_code=503, content={"detail": "Database is not configured. Set DATABASE_URL."})
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/setup", status_code=303)
        return JSONResponse(
            status_code=503, content={"detail": "The app is not configured yet. Open /setup in a browser."}
        )
