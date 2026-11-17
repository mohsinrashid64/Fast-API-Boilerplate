"""The admin "Database" page: status, migrations, and switching."""

import pytest
from dotenv import dotenv_values
from sqlalchemy import select

from app.core.config import settings
from app.core.db_admin import target_session
from app.models import User, UserAuth


@pytest.fixture
def env_path():
    path = settings.env_file_path
    path.unlink(missing_ok=True)
    yield path
    path.unlink(missing_ok=True)


async def _admin_client(client, make_user):
    await make_user("root", "password123", superuser=True)
    r = await client.post("/admin/login", data={"username": "root", "password": "password123"})
    assert r.status_code == 302


async def test_database_page_requires_login(client):
    assert (await client.get("/admin/database")).status_code == 302


async def test_database_page_and_migrate(client, make_user, env_path):
    await _admin_client(client, make_user)
    r = await client.get("/admin/database")
    assert r.status_code == 200
    assert "Connected" in r.text and "SQLite" in r.text
    # The test DB is built with create_all, so Alembic sees it as un-migrated.
    assert "pending" in r.text

    r = await client.post("/admin/database", data={"action": "migrate"})
    assert r.status_code == 303
    r = await client.get("/admin/database")
    assert "Migrations applied" in r.text and "Up to date" in r.text


async def test_switch_blocked_when_url_is_an_env_var(client, make_user, env_path, tmp_path):
    await _admin_client(client, make_user)  # conftest sets DATABASE_URL as an environment variable
    await client.post(
        "/admin/database",
        data={"action": "switch", "db_mode": "sqlite", "sqlite_path": str(tmp_path / "n.db"), "confirm": "yes"},
    )
    r = await client.get("/admin/database")
    assert "environment variable" in r.text
    assert not (tmp_path / "n.db").exists()


async def test_switch_prepares_new_db_and_needs_restart(client, make_user, env_path, tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    await _admin_client(client, make_user)
    new_db = tmp_path / "next.db"

    r = await client.post("/admin/database", data={"action": "test", "db_mode": "sqlite", "sqlite_path": str(new_db)})
    assert r.json()["ok"] and r.json()["will_create"]

    # Without confirmation nothing happens.
    await client.post("/admin/database", data={"action": "switch", "db_mode": "sqlite", "sqlite_path": str(new_db)})
    assert not new_db.exists()

    r = await client.post(
        "/admin/database",
        data={"action": "switch", "db_mode": "sqlite", "sqlite_path": str(new_db), "confirm": "yes"},
    )
    assert r.status_code == 303
    new_url = f"sqlite+aiosqlite:///{new_db}"
    assert dotenv_values(env_path)["DATABASE_URL"] == new_url

    # The admin account (and its password hash) was copied into the new database.
    async with target_session(new_url) as session:
        user = (await session.execute(select(User).where(User.username == "root"))).scalar_one()
        auth = (await session.execute(select(UserAuth).where(UserAuth.user_id == user.id))).scalar_one()
    assert user.is_superuser and auth.password_hash

    # This server keeps using the old DB until restart, and every admin page says so.
    r = await client.get("/admin/")
    assert "Restart required" in r.text and "next.db" in r.text
    assert (await client.get("/admin/user/list")).status_code == 200

    # Cancelling restores .env.
    await client.post("/admin/database", data={"action": "cancel-switch"})
    assert dotenv_values(env_path)["DATABASE_URL"] != new_url
    assert "Restart required" not in (await client.get("/admin/")).text


async def test_switch_rejects_bad_connection(client, make_user, env_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    await _admin_client(client, make_user)
    await client.post(
        "/admin/database",
        data={"action": "switch", "db_mode": "postgres", "database_url": "postgresql://u:p@127.0.0.1:1/x", "confirm": "yes"},
    )
    r = await client.get("/admin/database")
    assert "Could not connect" in r.text
    assert not env_path.exists() or "DATABASE_URL" not in dotenv_values(env_path)
