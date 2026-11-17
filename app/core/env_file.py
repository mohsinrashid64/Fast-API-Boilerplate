"""Read/update the `.env` file used by `settings` (keeps comments and ordering)."""

import logging
import os
import secrets

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

from app.core.config import reload_settings, settings

logger = logging.getLogger(__name__)

_last_mtime: float | None = None


def read_env() -> dict[str, str | None]:
    path = settings.env_file_path
    return dict(dotenv_values(path)) if path.exists() else {}


def update_env(values: dict[str, str]) -> None:
    """Set keys in `.env` (creating it with owner-only permissions if needed)."""
    path = settings.env_file_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
    for key, value in values.items():
        set_key(str(path), key, value, quote_mode="auto")


def ensure_secret_keys() -> None:
    """Generate SECRET_KEY / ENCRYPTION_KEY if missing (never in production without the wizard)."""
    if settings.is_production and not settings.setup_wizard_enabled:
        return
    new: dict[str, str] = {}
    if not settings.SECRET_KEY:
        new["SECRET_KEY"] = secrets.token_urlsafe(64)
    if not settings.ENCRYPTION_KEY:
        new["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    if new:
        update_env(new)
        reload_settings()
        logger.warning("Generated %s and saved to %s", ", ".join(new), settings.env_file_path)


def refresh_if_env_changed() -> bool:
    """Reload settings when `.env` changed on disk (e.g. setup finished in another worker).

    Returns True if settings were reloaded.
    """
    global _last_mtime
    try:
        mtime = settings.env_file_path.stat().st_mtime
    except FileNotFoundError:
        return False
    if mtime == _last_mtime:
        return False
    _last_mtime = mtime
    reload_settings()
    return True


def env_database_url() -> str | None:
    """DATABASE_URL as currently written in `.env` (may differ from the active one until restart)."""
    return read_env().get("DATABASE_URL") or None
