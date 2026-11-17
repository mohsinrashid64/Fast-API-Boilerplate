import re

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import ResetToken
from app.utils.crypto_util import decrypt_data, encrypt_data

SIGNUP = {
    "username": "alice",
    "email": "alice@gmail.com",
    "password": "password123",
    "confirm_password": "password123",
    "otp_type": "email",
}


def _otp_from(outbox) -> str:
    return re.search(r"\b(\d{6})\b", outbox[-1]["body"]).group(1)


async def test_signup_verify_login_me(client, outbox):
    r = await client.post("/auth/signup", json=SIGNUP)
    assert r.status_code == 201, r.text
    encrypted_id = r.json()["user_id"]
    assert outbox[-1]["to"] == "alice@gmail.com"

    # Unverified users get an OTP instead of a token.
    r = await client.post("/auth/login", json={"username_or_email_or_phone": "alice", "password": "password123"})
    assert "access_token" not in r.json()

    r = await client.post("/otp/verify", json={"user_id": encrypted_id, "otp_code": _otp_from(outbox)})
    assert r.status_code == 200, r.text

    r = await client.post(
        "/auth/login", json={"username_or_email_or_phone": "alice@gmail.com", "password": "password123"}
    )
    token = r.json()["access_token"]

    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert r.json()["is_verified"] is True


async def test_wrong_password_rejected(client, make_user):
    await make_user("bob")
    r = await client.post("/auth/login", json={"username_or_email_or_phone": "bob", "password": "nope-nope"})
    assert r.status_code == 400


async def test_duplicate_signup_rejected(client, outbox):
    assert (await client.post("/auth/signup", json=SIGNUP)).status_code == 201
    assert (await client.post("/auth/signup", json=SIGNUP)).status_code == 400


async def test_two_users_without_phone_can_sign_up(client, outbox):
    # Regression: the duplicate check used to match on phone_number IS NULL.
    assert (await client.post("/auth/signup", json=SIGNUP)).status_code == 201
    other = {**SIGNUP, "username": "carol", "email": "carol@gmail.com"}
    assert (await client.post("/auth/signup", json=other)).status_code == 201


@pytest.mark.parametrize(
    "override",
    [
        {"email": "x@unknown-provider.dev"},
        {"confirm_password": "different123"},
        {"password": "short", "confirm_password": "short"},
        {"otp_type": "phone"},  # phone required
    ],
)
async def test_signup_validation(client, outbox, override):
    r = await client.post("/auth/signup", json={**SIGNUP, **override})
    assert r.status_code == 422


async def test_otp_resend_and_bad_ids(client, outbox):
    r = await client.post("/auth/signup", json=SIGNUP)
    encrypted_id = r.json()["user_id"]
    first = _otp_from(outbox)

    r = await client.post("/otp/generate", json={"user_id": encrypted_id})
    assert r.status_code == 200, r.text
    second = _otp_from(outbox)

    # Old code is invalidated by the resend (unless the random codes collide).
    if first != second:
        r = await client.post("/otp/verify", json={"user_id": encrypted_id, "otp_code": first})
        assert r.status_code == 400

    r = await client.post("/otp/verify", json={"user_id": "garbage", "otp_code": "123456"})
    assert r.status_code == 400


async def test_forgot_and_reset_password(client, outbox, make_user):
    await make_user("dave", "oldpassword1")

    r = await client.post("/auth/forgot-password", json={"email": "nobody@gmail.com"})
    assert r.status_code == 200
    assert outbox == []  # nothing sent, but same response (no user enumeration)

    r = await client.post("/auth/forgot-password", json={"email": "dave@gmail.com"})
    assert r.status_code == 200
    async with AsyncSessionLocal() as session:
        token = (await session.execute(select(ResetToken.token))).scalar_one()
    assert token in outbox[-1]["body"]

    r = await client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "newpassword1", "confirm_password": "newpassword1"},
    )
    assert r.status_code == 200, r.text

    # Token is single-use.
    r = await client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "another1234", "confirm_password": "another1234"},
    )
    assert r.status_code == 400

    r = await client.post("/auth/login", json={"username_or_email_or_phone": "dave", "password": "newpassword1"})
    assert "access_token" in r.json()


async def test_inactive_user_cannot_use_token(client, make_user):
    from tests.conftest import auth_headers

    user = await make_user("eve", active=False)
    r = await client.get("/me", headers=auth_headers(user))
    assert r.status_code == 401


def test_encryption_round_trip_and_tamper():
    token = encrypt_data(42)
    assert decrypt_data(token) == 42
    with pytest.raises(ValueError):
        decrypt_data(token[:-4] + "AAAA")
