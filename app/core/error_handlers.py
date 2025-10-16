import os
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

ENV = "development"

def init_exception_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail or "HTTP error occurred"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def db_integrity_error_handler(request: Request, exc: IntegrityError):
        logger.error(str(exc))
        return JSONResponse(
            status_code=400,
            content={"detail": "Database integrity error"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(str(exc), exc_info=True)

        # ✅ Include the real message in dev mode
        detail = str(exc) if ENV == "development" else "Internal server error"
        return JSONResponse(
            status_code=500,
            content={"detail": detail},
        )
