from pathlib import Path

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import PROJECT_ROOT, settings


# Columns used to label a record when its model doesn't define __str__, in order.
_LABEL_COLUMNS = ("name", "title", "username", "label", "display_name", "full_name", "email", "slug", "code")


class Base(DeclarativeBase):
    def __str__(self) -> str:
        """Readable default label (admin lists, dropdowns, links) for any model.

        Uses only already-loaded column values, so it never triggers a lazy load
        (which isn't allowed with async sessions). Models can override it.
        """
        state = sa_inspect(self)
        loaded = state.dict
        for key in _LABEL_COLUMNS:
            value = loaded.get(key)
            if value not in (None, ""):
                return str(value)
        identity = state.identity
        pk = ", ".join(str(v) for v in identity) if identity else "new"
        return f"{type(self).__name__} #{pk}"


# Unbound until a database is configured; `init_engine()` binds it.
AsyncSessionLocal = async_sessionmaker(class_=AsyncSession, expire_on_commit=False)

_engine: AsyncEngine | None = None
_engine_url: str | None = None


class DatabaseNotConfigured(RuntimeError):
    pass


def connectable_url(url: str) -> str:
    """Resolve a relative SQLite path against the project root (not the current directory)."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        path = Path(parsed.database)
        if not path.is_absolute():
            parsed = parsed.set(database=str((PROJECT_ROOT / path).resolve()))
    return parsed.render_as_string(hide_password=False)


def init_engine(url: str) -> AsyncEngine:
    """Create the app engine for `url` and bind the session factory to it."""
    global _engine, _engine_url
    if _engine is not None and _engine_url == url:
        return _engine
    old = _engine
    _engine = create_async_engine(connectable_url(url), echo=settings.DB_ECHO)
    _engine_url = url
    if _engine.dialect.name == "sqlite":
        enable_sqlite_foreign_keys(_engine)
    AsyncSessionLocal.configure(bind=_engine)
    if old is not None:
        # Connections still in use finish normally; the pool is just released.
        old.sync_engine.dispose(close=False)
    return _engine


def enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores FOREIGN KEY / ON DELETE unless this is switched on per connection."""

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise DatabaseNotConfigured("No database configured. Open /setup or set DATABASE_URL.")
    return _engine


def active_database_url() -> str | None:
    return _engine_url


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()


async def get_db():
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


if settings.DATABASE_URL:
    init_engine(settings.DATABASE_URL)
