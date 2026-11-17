import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.database.db_config import Base, connectable_url
import app.models  # noqa: F401  -- registers all models on Base.metadata

config = context.config
# Programmatic callers (the app, tests) may pass a URL via `Config.attributes["database_url"]`.
DATABASE_URL = config.attributes.get("database_url") or settings.DATABASE_URL
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL is not configured. Set it in .env, or start the app and open /setup.")
config.set_main_option("sqlalchemy.url", connectable_url(DATABASE_URL).replace("%", "%%"))

# The app runs migrations in-process and keeps its own logging setup.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure_kwargs() -> dict:
    return {
        "target_metadata": target_metadata,
        # SQLite can't ALTER most things in place; batch mode recreates tables.
        "render_as_batch": DATABASE_URL.startswith("sqlite"),
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_configure_kwargs())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
