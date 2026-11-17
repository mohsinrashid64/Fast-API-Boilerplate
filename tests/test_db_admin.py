"""Unit tests for connection-string handling and migrations (temp SQLite files only)."""

import asyncio
import sqlite3

import pytest
from sqlalchemy import create_engine

from app.core.db_admin import (
    DatabaseConfigError,
    alembic_config,
    check_connection,
    migrate_to_head,
    migration_status,
    normalize_url,
    sqlite_url,
)
from app.database import Base


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("postgres://u:p@db.example.com/app", "postgresql+asyncpg://u:p@db.example.com/app"),
        ("postgresql://u:p@localhost:5432/app", "postgresql+asyncpg://u:p@localhost:5432/app"),
        (
            "postgresql://u:p@h/app?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@h/app?ssl=require",
        ),
        ("postgresql+psycopg2://u:p@h/app", "postgresql+asyncpg://u:p@h/app"),
        ("sqlite:///./data.db", "sqlite+aiosqlite:///./data.db"),
        ("  sqlite+aiosqlite:////tmp/x.db  ", "sqlite+aiosqlite:////tmp/x.db"),
    ],
)
def test_normalize_url_accepts(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw, message",
    [
        ("", "Enter a connection string"),
        ("not a url", "doesn't look like"),
        ("mysql://u:p@h/db", "Unsupported database"),
        ("postgresql://u:p@/db", "needs a host"),
        ("postgresql://u:p@h", "needs a database name"),
        ("sqlite://", "file path"),
    ],
)
def test_normalize_url_rejects(raw, message):
    with pytest.raises(DatabaseConfigError, match=message):
        normalize_url(raw)


def test_sqlite_url_helper():
    assert sqlite_url("data/app.db") == "sqlite+aiosqlite:///./data/app.db"
    assert sqlite_url("") == "sqlite+aiosqlite:///./power.db"
    assert sqlite_url("/abs/app.db") == "sqlite+aiosqlite:////abs/app.db"


async def test_new_sqlite_file_is_created_and_migrated(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'sub' / 'new.db'}"
    info = await check_connection(url)
    assert info["will_create"] and not (tmp_path / "sub" / "new.db").exists()  # testing doesn't create it

    status = await migrate_to_head(url)
    assert status["up_to_date"] and status["current"] == status["head"]

    info = await check_connection(url)
    assert info["app_tables"] and info["revision"] == status["head"]
    assert {"users", "products", "otps"} <= set(info["tables"])


async def test_unwritable_sqlite_location(tmp_path):
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    with pytest.raises(DatabaseConfigError, match="not writable"):
        await check_connection(f"sqlite+aiosqlite:///{blocker / 'x.db'}")


async def test_unreachable_postgres_gives_readable_error():
    with pytest.raises(DatabaseConfigError, match="Could not connect"):
        await check_connection("postgresql+asyncpg://u:p@127.0.0.1:1/nope")


async def test_legacy_create_all_database_is_stamped_not_recreated(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)  # how the app used to create tables (no alembic_version)
    engine.dispose()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO users (username, email, is_verified, is_active, is_superuser) VALUES ('old', 'o@gmail.com', 1, 1, 0)")

    status = await migrate_to_head(f"sqlite+aiosqlite:///{path}")
    assert status["up_to_date"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT username FROM users").fetchall() == [("old",)]


async def test_old_schema_without_admin_columns_is_upgraded(tmp_path):
    from alembic import command

    path = tmp_path / "old.db"
    url = f"sqlite+aiosqlite:///{path}"
    await asyncio.to_thread(command.upgrade, alembic_config(url), "0001")
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE alembic_version")  # simulate the pre-Alembic database

    status = await migrate_to_head(url)
    assert status["up_to_date"]
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    assert {"is_active", "is_superuser"} <= columns


async def test_migration_status_reports_pending(tmp_path):
    from alembic import command

    url = f"sqlite+aiosqlite:///{tmp_path / 'p.db'}"
    await asyncio.to_thread(command.upgrade, alembic_config(url), "0001")
    status = await migration_status(url)
    assert status["current"] == "0001"
    pending = [r["revision"] for r in status["pending"]]
    assert "0002" in pending and "0001" not in pending  # later migrations (generated tables) may follow
