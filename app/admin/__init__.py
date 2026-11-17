from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from sqladmin.authentication import login_required
from sqladmin.authorization import Action
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from starlette.responses import Response

from app.admin.auth import AdminAuth
from app.admin.database import DatabaseView, pending_switch_url
from app.admin.erd import SchemaView
from app.admin.views import all_views
from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models import OTP, Product, User
from app.core.db_admin import mask_url
from app.utils.time import utc_in, utcnow

TEMPLATES_DIR = Path(__file__).parent / "templates"
LOW_STOCK = 10  # products below this many units are flagged on the dashboard


class AppAdmin(Admin):
    """sqladmin's Admin with a dashboard landing page and paged relationship lookups."""

    @login_required
    async def ajax_lookup(self, request: Request) -> Response:
        """Like sqladmin's lookup, but an empty term lists records and results are paged."""
        model_view = self._find_model_view(request.path_params["identity"])
        if not model_view.is_accessible(request):
            raise HTTPException(status_code=403)
        can_use_form = (
            model_view.can_create and await model_view.check_can_create(request)
        ) or (model_view.can_edit and model_view.has_permission(request, Action.EDIT))
        if not can_use_form:
            raise HTTPException(status_code=403)

        loader = model_view._form_ajax_refs.get(request.query_params.get("name", ""))
        if loader is None:
            raise HTTPException(status_code=400)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1

        rows, more = await loader.get_page(request, request.query_params.get("term", ""), page)
        return JSONResponse({"results": [loader.format(m) for m in rows], "pagination": {"more": more}})

    @login_required
    async def index(self, request: Request) -> Response:
        async with AsyncSessionLocal() as session:
            async def scalar(stmt):
                return (await session.execute(stmt)).scalar_one()

            users = await scalar(select(func.count(User.id)))
            verified = await scalar(select(func.count(User.id)).where(User.is_verified.is_(True)))
            stats = {
                "users": users,
                "new_users": await scalar(select(func.count(User.id)).where(User.created_at >= utc_in(days=-7))),
                "verified": verified,
                "verified_pct": round(verified * 100 / users) if users else 0,
                "superusers": await scalar(select(func.count(User.id)).where(User.is_superuser.is_(True))),
                "products": await scalar(select(func.count(Product.id))),
                "units": await scalar(select(func.coalesce(func.sum(Product.stock), 0))),
                "low_stock": await scalar(select(func.count(Product.id)).where(Product.stock < LOW_STOCK)),
                "pending_otps": await scalar(
                    select(func.count(OTP.id)).where(OTP.verified.is_(False), OTP.expires_at > utcnow())
                ),
            }
            recent_users = (await session.execute(select(User).order_by(User.id.desc()).limit(6))).scalars().all()
            recent_products = (
                await session.execute(
                    select(Product).options(selectinload(Product.user)).order_by(Product.id.desc()).limit(6)
                )
            ).scalars().all()

        return await self.templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "stats": stats,
                "low_stock_threshold": LOW_STOCK,
                "recent_users": recent_users,
                "recent_products": recent_products,
            },
        )


def setup_admin(app: FastAPI) -> AppAdmin:
    """Mount the admin panel at /admin (login: an active superuser)."""
    admin = AppAdmin(
        app,
        session_maker=AsyncSessionLocal,  # bound lazily: works before a DB is configured
        title=settings.APP_NAME,
        templates_dir=str(TEMPLATES_DIR),
        authentication_backend=AdminAuth(
            secret_key=settings.SECRET_KEY,
            https_only=settings.is_production,
            same_site="lax",
            max_age=60 * 60 * 8,  # 8h admin session
        ),
    )
    admin.add_view(SchemaView)  # ER diagram, listed right under Dashboard
    admin.add_view(DatabaseView)  # connection, migrations, switch database
    # Shown as a banner on every admin page while a database switch awaits a restart.
    admin.templates.env.globals["pending_db_switch"] = lambda: mask_url(pending_switch_url())
    for view in all_views():
        admin.add_view(view)
    return admin
