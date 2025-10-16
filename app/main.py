# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.error_handlers import init_exception_handlers
from app.core.config import settings
from app.routes import router as api_router
from app.middlewares import init_middlewares
from app.database import create_database

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
    )
    create_database()
    # Global exception handlers
    init_exception_handlers(app)

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    init_middlewares(app)

    # Routers
    app.include_router(api_router)


    # Health check
    @app.get("/", tags=["Health Check"])
    def health_check():
        return {"status": "ok", "message": "API is running successfully"}

    return app


app = create_app()
