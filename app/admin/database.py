import logging

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.admin.auth import SESSION_KEY
from app.core.config import settings
from app.core.db_admin import (
    DatabaseConfigError,
    backend,
    check_connection,
    mask_url,
    migrate_to_head,
    migration_status,
    normalize_url,
    sqlite_url,
    target_session,
)
from app.core.env_file import env_database_url, update_env
from app.database import AsyncSessionLocal, active_database_url
from app.services.bootstrap import copy_superuser

logger = logging.getLogger(__name__)
FLASH_KEY = "db_flash"


def switch_blocked_reason() -> str | None:
    if not settings.db_switch_enabled:
        return "Switching databases from the admin is turned off in production. Set ALLOW_DB_SWITCH=true to enable it."
    if settings.database_url_from_environment:
        return (
            "DATABASE_URL is set as an environment variable, which always takes priority over .env. "
            "Change it where your server's environment is configured."
        )
    return None


def pending_switch_url() -> str | None:
    """The DATABASE_URL saved in .env when it differs from the one this process is using."""
    if settings.database_url_from_environment:
        return None
    saved = env_database_url()
    return saved if saved and saved != active_database_url() else None


def _url_from_form(form) -> str:
    if form.get("db_mode") == "postgres":
        return normalize_url(str(form.get("database_url", "")))
    return sqlite_url(str(form.get("sqlite_path", "")))


def _flash(request: Request, kind: str, message: str) -> None:
    request.session[FLASH_KEY] = {"kind": kind, "message": message}


class DatabaseView(BaseView):
    """Connection info, migrations, and a guarded "switch database" flow."""

    name = "Database"
    icon = "fa-solid fa-database"

    @expose("/database", methods=["GET", "POST"], identity="database")
    async def database_page(self, request: Request) -> Response:
        if request.method == "POST":
            return await self._handle_post(request)

        active = active_database_url()
        info, status, error = None, None, None
        try:
            info = await check_connection(active)
            status = await migration_status(active, current=info["revision"])
        except DatabaseConfigError as exc:
            error = str(exc)

        pending = pending_switch_url()
        return await self.templates.TemplateResponse(
            request,
            "database.html",
            {
                "title": "Database",
                "subtitle": "Connection, migrations and switching to another database.",
                "active_url": mask_url(active),
                "backend": backend(active),
                "info": info,
                "status": status,
                "error": error,
                "pending_url": mask_url(pending) if pending else None,
                "switch_blocked": switch_blocked_reason(),
                "flash": request.session.pop(FLASH_KEY, None),
            },
        )

    async def _handle_post(self, request: Request) -> Response:
        form = await request.form()
        action = form.get("action")
        back = RedirectResponse(request.url_for("admin:view-database"), status_code=303)
        active = active_database_url()

        if action == "test":
            try:
                url = _url_from_form(form)
                return JSONResponse({**await check_connection(url), "url": mask_url(url)})
            except DatabaseConfigError as exc:
                return JSONResponse({"ok": False, "error": str(exc)})

        if action == "migrate":
            try:
                status = await migrate_to_head(active)
                _flash(request, "success", f"Migrations applied. The database is at revision {status['current']}.")
            except DatabaseConfigError as exc:
                _flash(request, "error", str(exc))
            return back

        if action == "cancel-switch":
            if pending_switch_url():
                update_env({"DATABASE_URL": active})
                _flash(request, "success", "Switch cancelled. .env points at the current database again.")
            return back

        if action == "switch":
            reason = switch_blocked_reason()
            if reason:
                _flash(request, "error", reason)
                return back
            try:
                url = _url_from_form(form)
                if url == active:
                    raise DatabaseConfigError("That's the database you're already using.")
                if form.get("confirm") != "yes":
                    raise DatabaseConfigError("Tick the confirmation box to switch.")
                status = await migrate_to_head(url)
                async with AsyncSessionLocal() as source, target_session(url) as target:
                    copied = await copy_superuser(source, int(request.session[SESSION_KEY]), target)
            except (DatabaseConfigError, ValueError) as exc:
                _flash(request, "error", str(exc))
                return back

            update_env({"DATABASE_URL": url})
            logger.warning("Admin switched DATABASE_URL in .env to %s (restart required)", mask_url(url))
            _flash(
                request,
                "success",
                f"The new database is ready (migration {status['current']}) and {copied}. "
                "Restart the server to start using it.",
            )
            return back

        _flash(request, "error", "Unknown action.")
        return back
