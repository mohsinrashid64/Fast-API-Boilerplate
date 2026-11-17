import ipaddress
import re
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from app.core.config import reload_settings, settings
from app.core.db_admin import (
    DatabaseConfigError,
    check_connection,
    mask_url,
    migrate_to_head,
    normalize_url,
    sqlite_url,
    target_session,
)
from app.core.env_file import update_env
from app.database import init_engine
from app.services.bootstrap import create_or_promote_superuser

_HERE = Path(__file__).parent
templates = Jinja2Templates(
    env=Environment(
        loader=ChoiceLoader(
            [FileSystemLoader(_HERE / "templates"), FileSystemLoader(_HERE.parent / "admin" / "templates")]
        ),
        autoescape=select_autoescape(["html"]),
    )
)

router = APIRouter(include_in_schema=False)

_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")


def _guard(request: Request) -> None:
    """The wizard only exists until the app is configured, and only for this machine."""
    if settings.is_configured or not settings.setup_wizard_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.SETUP_ALLOW_REMOTE:
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == "localhost"
        if not local:
            raise HTTPException(
                status_code=403,
                detail="Setup is only available from this machine (localhost). "
                "Set SETUP_ALLOW_REMOTE=true to allow it from other hosts.",
            )


def _url_from_form(form) -> str:
    if form.get("db_mode") == "postgres":
        return normalize_url(str(form.get("database_url", "")))
    return sqlite_url(str(form.get("sqlite_path", "")))


def _render(request: Request, values: dict, error: str | None = None, status: int = 200):
    return templates.TemplateResponse(
        request, "setup.html", {"values": values, "error": error, "app_name": settings.APP_NAME}, status_code=status
    )


@router.get("/setup")
async def setup_page(request: Request):
    _guard(request)
    return _render(request, {"db_mode": "sqlite", "sqlite_path": "./power.db"})


@router.post("/setup/test")
async def setup_test(request: Request):
    _guard(request)
    form = await request.form()
    try:
        url = _url_from_form(form)
        info = await check_connection(url)
    except DatabaseConfigError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})
    return JSONResponse({**info, "url": mask_url(url)})


@router.post("/setup")
async def setup_submit(request: Request):
    _guard(request)
    form = await request.form()
    values = {k: str(v) for k, v in form.items() if "password" not in k}

    try:
        url = _url_from_form(form)

        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        if not _USERNAME.match(username):
            raise DatabaseConfigError("Username must be 3–50 letters, numbers, dots, dashes or underscores.")
        try:
            email = validate_email(str(form.get("email", "")).strip(), check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise DatabaseConfigError(f"Email: {exc}")
        if not 8 <= len(password) <= 72:
            raise DatabaseConfigError("Password must be 8–72 characters.")
        if password != form.get("password_confirm"):
            raise DatabaseConfigError("Passwords do not match.")

        await migrate_to_head(url)
        async with target_session(url) as session:
            await create_or_promote_superuser(session, username, email, password)
    except DatabaseConfigError as exc:
        return _render(request, values, error=str(exc), status=400)

    # Save, then switch this process over (no restart needed: nothing was using a database yet).
    update_env({"DATABASE_URL": url})
    reload_settings()
    init_engine(url)
    return RedirectResponse("/admin/login?setup=1", status_code=303)
