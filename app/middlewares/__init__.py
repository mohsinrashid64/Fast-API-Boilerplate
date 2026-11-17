from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def init_middlewares(app: FastAPI) -> None:
    """Register all middlewares.

    Authentication is NOT done here: protected routes declare
    `Depends(get_current_user)` (see app/core/deps.py), which also shows the
    lock icon in /docs. The admin panel has its own session-based login.
    """
    origins = settings.cors_origins_list
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Browsers reject credentials with a wildcard origin.
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )
