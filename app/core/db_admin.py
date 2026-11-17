"""Database operations used by the setup wizard and the admin "Database" page:
normalize/test connection strings, inspect migration state and run migrations.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import PROJECT_ROOT
from app.database import connectable_url

CONNECT_TIMEOUT = 8  # seconds

_DRIVERS = {
    "sqlite": "sqlite+aiosqlite",
    "sqlite+aiosqlite": "sqlite+aiosqlite",
    "sqlite+pysqlite": "sqlite+aiosqlite",
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "postgresql+asyncpg": "postgresql+asyncpg",
    "postgresql+psycopg2": "postgresql+asyncpg",
    "postgresql+psycopg": "postgresql+asyncpg",
}


class DatabaseConfigError(ValueError):
    """A user-facing problem with a connection string or database."""


# ---------------------------------------------------------------- URLs
def normalize_url(raw: str) -> str:
    """Validate a user-supplied connection string and convert it to the app's async driver.

    Accepts e.g. `postgres://u:p@host/db`, `postgresql://...?sslmode=require`,
    `sqlite:///./app.db`. Raises DatabaseConfigError with a readable message.
    """
    raw = (raw or "").strip()
    if not raw:
        raise DatabaseConfigError("Enter a connection string.")
    try:
        url = make_url(raw)
    except ArgumentError:
        raise DatabaseConfigError(
            "That doesn't look like a connection string. Example: postgresql://user:password@localhost:5432/mydb"
        )

    driver = _DRIVERS.get(url.drivername)
    if driver is None:
        raise DatabaseConfigError(f"Unsupported database '{url.drivername}'. Use SQLite or PostgreSQL.")
    url = url.set(drivername=driver)

    if driver.startswith("sqlite"):
        if not url.database or url.database == ":memory:":
            raise DatabaseConfigError("Give the SQLite database a file path, e.g. ./power.db")
    else:
        if not url.host:
            raise DatabaseConfigError("The PostgreSQL connection string needs a host.")
        if not url.database:
            raise DatabaseConfigError("The PostgreSQL connection string needs a database name (…/dbname).")
        url = _asyncpg_query(url)

    return url.render_as_string(hide_password=False)


def _asyncpg_query(url: URL) -> URL:
    """Translate libpq-style query options (as used by Heroku, Neon, Supabase...) to asyncpg."""
    query = dict(url.query)
    if "sslmode" in query:
        query["ssl"] = query.pop("sslmode")
    for unsupported in ("channel_binding", "options", "application_name"):
        query.pop(unsupported, None)
    return url.set(query=query)


def sqlite_url(path: str) -> str:
    path = (path or "").strip() or "./power.db"
    if not path.startswith(("/", "./", "../")):
        path = "./" + path
    return normalize_url(f"sqlite:///{path}")


def mask_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return "(invalid URL)"


def backend(url: str) -> str:
    return make_url(url).get_backend_name()  # "sqlite" | "postgresql"


def _sqlite_path(url: str) -> Path:
    return Path(make_url(connectable_url(url)).database)


# ---------------------------------------------------------------- connections
def _engine(url: str):
    is_pg = backend(url) == "postgresql"
    return create_async_engine(
        connectable_url(url),
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT} if is_pg else {},
    )


@asynccontextmanager
async def target_session(url: str) -> AsyncIterator[AsyncSession]:
    """A short-lived session on an arbitrary database (not the app's active one)."""
    engine = _engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _friendly(exc: BaseException) -> str:
    """First line of the underlying driver error, or a plain-language hint."""
    text_ = str(getattr(exc, "orig", None) or exc).strip()
    message = text_.splitlines()[0] if text_ else type(exc).__name__
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "Timed out connecting to the database server."
    if isinstance(exc, ConnectionRefusedError) or "Connect call failed" in message:
        return "Connection refused: is the database server running and reachable?"
    return message[:300]


async def check_connection(url: str) -> dict[str, Any]:
    """Connect and describe the database. Raises DatabaseConfigError if it can't connect.

    A SQLite file that doesn't exist yet is reported as `will_create` instead of being created.
    """
    kind = backend(url)
    if kind == "sqlite":
        path = _sqlite_path(url)
        if not path.exists():
            ancestor = path.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            if not ancestor.is_dir() or not os.access(ancestor, os.W_OK):
                raise DatabaseConfigError(f"Can't create a database file in {path.parent} (not writable).")
            return {
                "ok": True, "backend": kind, "will_create": True, "path": str(path),
                "server_version": None, "tables": [], "app_tables": False,
                "revision": None, "size_bytes": 0,
            }

    engine = _engine(url)
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT + 2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                version_info = conn.dialect.server_version_info or ()
                tables = await conn.run_sync(lambda c: sorted(inspect(c).get_table_names()))
                revision = None
                if "alembic_version" in tables:
                    revision = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                if kind == "postgresql":
                    size = (await conn.execute(text("SELECT pg_database_size(current_database())"))).scalar()
                else:
                    size = _sqlite_path(url).stat().st_size
    except DatabaseConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced to the user
        raise DatabaseConfigError(f"Could not connect: {_friendly(exc)}") from exc
    finally:
        await engine.dispose()

    app_tables = {"users", "user_auth"}.issubset(tables)
    return {
        "ok": True,
        "backend": kind,
        "will_create": False,
        "path": str(_sqlite_path(url)) if kind == "sqlite" else None,
        "server_version": ".".join(str(v) for v in version_info) or None,
        "tables": [t for t in tables if t != "alembic_version"],
        "app_tables": app_tables,
        "revision": revision,
        "size_bytes": size,
    }


# ---------------------------------------------------------------- migrations
def alembic_config(url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False  # don't let alembic reset the app's logging
    return cfg


async def migration_status(url: str, current: str | None = None) -> dict[str, Any]:
    """Compare the database's revision with the migration scripts.

    Pass `current` when it's already known (avoids another connection).
    """
    script = ScriptDirectory.from_config(alembic_config(url))
    if current is None:
        current = (await check_connection(url)).get("revision")

    applied: set[str] = set()
    if current:
        applied = {rev.revision for rev in script.iterate_revisions(current, "base")}

    revisions = [
        {
            "revision": rev.revision,
            "message": (rev.doc or "").strip(),
            "applied": rev.revision in applied,
            "is_head": rev.revision in script.get_heads(),
        }
        for rev in script.walk_revisions()  # newest first
    ]
    pending = [r for r in revisions if not r["applied"]]
    return {
        "current": current,
        "head": script.get_current_head(),
        "revisions": revisions,
        "pending": pending,
        "up_to_date": not pending,
    }


async def migrate_to_head(url: str) -> dict[str, Any]:
    """Bring the database to the latest migration (creating the SQLite file if needed).

    Databases created by the old `create_all` code (tables but no `alembic_version`)
    are stamped first so their existing tables aren't re-created.
    """
    if backend(url) == "sqlite":
        _sqlite_path(url).parent.mkdir(parents=True, exist_ok=True)

    cfg = alembic_config(url)
    info = await check_connection(url)
    if info["app_tables"] and not info["revision"]:
        engine = _engine(url)
        try:
            async with engine.connect() as conn:
                user_cols = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("users")})
        finally:
            await engine.dispose()
        await asyncio.to_thread(command.stamp, cfg, "head" if "is_superuser" in user_cols else "0001")

    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:  # noqa: BLE001
        raise DatabaseConfigError(f"Migration failed: {_friendly(exc)}") from exc
    return await migration_status(url)
