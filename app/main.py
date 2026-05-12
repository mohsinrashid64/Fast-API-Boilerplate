from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.error_handlers import init_exception_handlers
from app.core.config import settings
from app.routes import router as api_router
from app.middlewares import init_middlewares
from app.database import create_database
from app.database.db_config import AsyncSessionLocal
from app.models import Role, Permission


DESCRIPTION = """
## Role-Based Access Control (RBAC) API

This API provides a complete authentication and authorization system with:

- **JWT Access Tokens** (30 min expiry) with roles & permissions in claims
- **JWT Refresh Tokens** (7 day expiry) with automatic rotation
- **Role-Based Access Control** — define roles (admin, editor, viewer, etc.) and assign them to users
- **Permission-Based Access Control** — attach fine-grained permissions (e.g. `products:read`, `products:write`) to roles
- **OTP Verification** — email/phone verification during signup
- **Password Reset** — token-based password recovery via email

### Default Roles (seeded on first startup)
| Role | Permissions |
|------|------------|
| **admin** | Full access to all resources |
| **user** | `products:read`, `products:write`, `products:delete` |
| **viewer** | `products:read` |
"""


async def seed_roles_and_permissions():
    """Seed default roles and permissions on first startup."""
    async with AsyncSessionLocal() as db:
        # Check if roles already exist
        result = await db.execute(select(Role).limit(1))
        if result.scalar_one_or_none():
            return  # Already seeded

        # Create permissions
        permissions = {
            "products:read": Permission(name="products:read", description="Read products"),
            "products:write": Permission(name="products:write", description="Create and update products"),
            "products:delete": Permission(name="products:delete", description="Delete products"),
            "users:manage": Permission(name="users:manage", description="Manage users"),
            "roles:manage": Permission(name="roles:manage", description="Manage roles and permissions"),
        }
        for perm in permissions.values():
            db.add(perm)
        await db.flush()

        # Create roles with permissions
        admin_role = Role(
            name="admin",
            description="Full access administrator",
            permissions=list(permissions.values()),
        )
        user_role = Role(
            name="user",
            description="Standard user with product access",
            permissions=[permissions["products:read"], permissions["products:write"], permissions["products:delete"]],
        )
        viewer_role = Role(
            name="viewer",
            description="Read-only access to products",
            permissions=[permissions["products:read"]],
        )

        db.add_all([admin_role, user_role, viewer_role])
        await db.commit()
        print("Default roles and permissions seeded successfully.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=DESCRIPTION,
        debug=settings.DEBUG,
        version="2.0.0",
    )

    @app.on_event("startup")
    async def on_startup():
        await create_database()
        await seed_roles_and_permissions()

    init_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    init_middlewares(app)

    app.include_router(api_router)

    @app.get(
        "/",
        tags=["Health Check"],
        summary="Health check",
        description="Returns the current status of the API. Use this to verify the service is running.",
    )
    def health_check():
        return {"status": "ok", "message": "API is running successfully"}

    return app


app = create_app()
