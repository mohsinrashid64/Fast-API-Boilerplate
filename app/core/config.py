import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_env_file() -> Path:
    """`.env` lives in the project root unless ENV_FILE points elsewhere."""
    path = Path(os.environ.get("ENV_FILE", ".env"))
    return path if path.is_absolute() else PROJECT_ROOT / path


ENV_FILE_PATH = _resolve_env_file()


class Settings(BaseSettings):
    """Application settings, loaded from environment variables and `.env`.

    Real environment variables always take precedence over `.env`.
    Every module should read configuration from `settings` instead of `os.getenv`.
    """

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "FastAPI Async Boilerplate"
    ENVIRONMENT: str = "development"  # development | production
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    WORKERS: int = 4
    CORS_ORIGINS: str = "http://localhost:3000"  # comma separated, or "*"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Security (generated automatically outside production when missing) ---
    SECRET_KEY: str | None = Field(None, min_length=32)
    ENCRYPTION_KEY: str | None = None  # Fernet key
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    JWT_ALGORITHM: str = "HS256"

    # --- Database ---
    # Empty = not configured yet: the app starts in setup mode (open /setup).
    DATABASE_URL: str | None = None
    DB_ECHO: bool = False

    # --- Database setup from the UI ---
    ALLOW_SETUP_WIZARD: bool | None = None  # default: on outside production
    SETUP_ALLOW_REMOTE: bool = False  # /setup only answers localhost unless true
    ALLOW_DB_SWITCH: bool | None = None  # admin "switch database"; default: on outside production

    # --- Email (SMTP) ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    EMAIL_CHECK_MX: bool = True

    # --- SMS (AWS SNS) ---
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "us-east-2"

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def setup_wizard_enabled(self) -> bool:
        return self.ALLOW_SETUP_WIZARD if self.ALLOW_SETUP_WIZARD is not None else not self.is_production

    @property
    def db_switch_enabled(self) -> bool:
        return self.ALLOW_DB_SWITCH if self.ALLOW_DB_SWITCH is not None else not self.is_production

    @property
    def is_configured(self) -> bool:
        return bool(self.DATABASE_URL and self.SECRET_KEY and self.ENCRYPTION_KEY)

    @property
    def database_url_from_environment(self) -> bool:
        """True when DATABASE_URL is a real environment variable (so `.env` can't override it)."""
        return bool(os.environ.get("DATABASE_URL"))

    @property
    def env_file_path(self) -> Path:
        return ENV_FILE_PATH

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_config_in_production(self) -> "Settings":
        if self.is_production and not self.setup_wizard_enabled:
            missing = [k for k in ("DATABASE_URL", "SECRET_KEY", "ENCRYPTION_KEY") if not getattr(self, k)]
            if missing:
                raise ValueError(f"Missing required settings in production: {', '.join(missing)}")
        return self


def _load() -> Settings:
    return Settings(_env_file=ENV_FILE_PATH)


settings = _load()


def reload_settings() -> Settings:
    """Re-read env vars and `.env`, updating the shared `settings` object in place
    (so every module that imported it sees the new values)."""
    fresh = _load()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(fresh, name))
    return settings
