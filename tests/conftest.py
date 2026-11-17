"""Test setup: an isolated SQLite DB, mocked email/SMS, and helper factories.

Environment variables are set *before* the app is imported so that `settings`
and the DB engine pick them up.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

_TMP_DIR = Path(tempfile.mkdtemp(prefix="fastapi-boilerplate-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "ENV_FILE": str(_TMP_DIR / ".env"),  # never touch the real .env
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP_DIR / 'test.db'}",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "EMAIL_CHECK_MX": "false",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "DB_ECHO": "false",
    }
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import AsyncSessionLocal, Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserAuth  # noqa: E402
from app.utils.hashing import Hash  # noqa: E402
from app.utils.jwt import create_access_token  # noqa: E402


@pytest.fixture(autouse=True)
async def reset_db():
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
def outbox(monkeypatch):
    """Capture outgoing emails/SMS instead of sending them."""
    sent: list[dict] = []

    async def fake_send_email(to, subject, body, html=False):
        sent.append({"channel": "email", "to": to, "subject": subject, "body": body})

    async def fake_send_sms(to, message):
        sent.append({"channel": "sms", "to": to, "body": message})
        return {"status": "success"}

    monkeypatch.setattr("app.services.otp_service.send_email", fake_send_email)
    monkeypatch.setattr("app.services.otp_service.send_sms", fake_send_sms)
    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)
    return sent


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def make_user():
    async def _make_user(
        username: str,
        password: str = "password123",
        *,
        email: str | None = None,
        superuser: bool = False,
        verified: bool = True,
        active: bool = True,
    ) -> User:
        async with AsyncSessionLocal() as session:
            user = User(
                username=username,
                email=email or f"{username}@gmail.com",
                is_superuser=superuser,
                is_verified=verified,
                is_active=active,
            )
            user.auth.append(UserAuth(auth_provider="password", password_hash=Hash.hash(password)))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return _make_user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
