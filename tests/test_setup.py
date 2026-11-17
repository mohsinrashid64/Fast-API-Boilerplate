"""The /setup wizard on an app with no database configured."""

import pytest
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient

import app.database.db_config as db_config
from app.core import env_file
from app.core.config import settings
from app.database import AsyncSessionLocal
from app.main import app


@pytest.fixture
async def unconfigured(monkeypatch):
    """Temporarily make the running app look like a fresh, unconfigured install."""
    env_path = settings.env_file_path
    original_env = env_path.read_text() if env_path.exists() else None
    if env_path.exists():
        env_path.unlink()
    saved = (settings.DATABASE_URL, db_config._engine, db_config._engine_url)

    monkeypatch.delenv("DATABASE_URL")
    settings.DATABASE_URL = None
    db_config._engine, db_config._engine_url = None, None
    AsyncSessionLocal.configure(bind=None)
    env_file._last_mtime = None
    yield env_path

    if db_config._engine is not None and db_config._engine is not saved[1]:
        await db_config._engine.dispose()
    settings.DATABASE_URL, db_config._engine, db_config._engine_url = saved
    AsyncSessionLocal.configure(bind=saved[1])
    env_file._last_mtime = None
    if original_env is None:
        env_path.unlink(missing_ok=True)
    else:
        env_path.write_text(original_env)


ADMIN = {"username": "owner", "email": "owner@gmail.com", "password": "ownerpass123", "password_confirm": "ownerpass123"}


async def test_unconfigured_app_redirects_to_setup(unconfigured, client):
    r = await client.get("/admin/", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"] == "/setup"
    r = await client.get("/products/")
    assert r.status_code == 503 and "/setup" in r.json()["detail"]
    r = await client.get("/setup")
    assert r.status_code == 200 and "Create database" in r.text


async def test_setup_test_endpoint(unconfigured, client, tmp_path):
    r = await client.post("/setup/test", data={"db_mode": "sqlite", "sqlite_path": str(tmp_path / "w.db")})
    assert r.json()["ok"] and r.json()["will_create"]
    r = await client.post("/setup/test", data={"db_mode": "postgres", "database_url": "mysql://x@y/z"})
    assert not r.json()["ok"] and "Unsupported" in r.json()["error"]


async def test_setup_validation_errors_keep_values(unconfigured, client, tmp_path):
    r = await client.post(
        "/setup",
        data={"db_mode": "sqlite", "sqlite_path": str(tmp_path / "v.db"), **ADMIN, "password_confirm": "different123"},
    )
    assert r.status_code == 400
    assert "Passwords do not match" in r.text and 'value="owner"' in r.text
    assert not (tmp_path / "v.db").exists()


async def test_full_setup_with_sqlite(unconfigured, client, tmp_path):
    db_path = tmp_path / "fresh.db"
    r = await client.post("/setup", data={"db_mode": "sqlite", "sqlite_path": str(db_path), **ADMIN})
    assert r.status_code == 303 and r.headers["location"] == "/admin/login?setup=1"

    assert db_path.exists()
    assert dotenv_values(unconfigured)["DATABASE_URL"] == f"sqlite+aiosqlite:///{db_path}"
    assert settings.is_configured

    # The wizard is gone and the new admin account works right away (no restart).
    assert (await client.get("/setup")).status_code == 404
    r = await client.post("/admin/login", data={"username": "owner", "password": "ownerpass123"})
    assert r.status_code == 302
    assert (await client.get("/admin/user/list")).status_code == 200


async def test_setup_refuses_remote_clients(unconfigured):
    transport = ASGITransport(app=app, client=("10.1.2.3", 5555))
    async with AsyncClient(transport=transport, base_url="http://test") as remote:
        assert (await remote.get("/setup")).status_code == 403


async def test_setup_is_404_once_configured(client):
    assert (await client.get("/setup")).status_code == 404
