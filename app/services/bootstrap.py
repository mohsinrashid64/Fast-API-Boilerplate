"""Create or copy admin (superuser) accounts. Used by the CLI, the setup wizard
and the admin "switch database" flow."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserAuth
from app.utils.hashing import Hash


async def _password_auth(session: AsyncSession, user_id: int) -> UserAuth | None:
    return (
        await session.execute(
            select(UserAuth).where(UserAuth.user_id == user_id, UserAuth.auth_provider == "password")
        )
    ).scalars().first()


async def create_or_promote_superuser(
    session: AsyncSession, username: str, email: str, password: str
) -> tuple[User, bool]:
    """Create a superuser, or promote the existing user with that username/email
    (resetting their password). Returns (user, created)."""
    email = email.strip().lower()
    user = (
        await session.execute(select(User).where(or_(User.username == username, User.email == email)))
    ).scalars().first()

    created = user is None
    if created:
        user = User(username=username, email=email)
        session.add(user)

    user.is_superuser = True
    user.is_active = True
    user.is_verified = True
    await session.flush()

    user_auth = await _password_auth(session, user.id)
    if user_auth:
        user_auth.password_hash = Hash.hash(password)
    else:
        session.add(UserAuth(user_id=user.id, auth_provider="password", password_hash=Hash.hash(password)))

    await session.commit()
    return user, created


async def copy_superuser(source: AsyncSession, user_id: int, target: AsyncSession) -> str:
    """Copy an admin account (with its password) into another database so the same
    login works after switching. If the target already has that user, it's promoted
    and keeps its own password. Returns a short description of what happened."""
    src_user = await source.get(User, user_id)
    if src_user is None:
        raise ValueError("Your admin account was not found in the current database.")
    src_auth = await _password_auth(source, user_id)

    existing = (
        await target.execute(
            select(User).where(or_(User.username == src_user.username, User.email == src_user.email))
        )
    ).scalars().first()
    if existing:
        existing.is_superuser = True
        existing.is_active = True
        existing.is_verified = True
        await target.commit()
        return f"'{existing.username}' already exists there and was made a superuser (its password is unchanged)"

    user = User(
        username=src_user.username,
        email=src_user.email,
        is_verified=True,
        is_active=True,
        is_superuser=True,
    )
    if src_auth and src_auth.password_hash:
        user.auth.append(UserAuth(auth_provider="password", password_hash=src_auth.password_hash))
    target.add(user)
    await target.commit()
    return f"'{user.username}' was copied there with your current password"
