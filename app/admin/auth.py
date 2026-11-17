from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import or_, select
from starlette.requests import Request

from app.database import AsyncSessionLocal
from app.models import User, UserAuth
from app.utils.hashing import Hash

# Session key; sqladmin's default `get_user_id` reads this same key (used for audit logs).
SESSION_KEY = "user_id"


async def _get_admin_user(user_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
    if user and user.is_active and user.is_superuser:
        return user
    return None


class AdminAuth(AuthenticationBackend):
    """Session-based login for the admin panel: only active superusers may enter."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        identifier = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        if not identifier or not password:
            return False

        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(
                    select(User).where(or_(User.username == identifier, User.email == identifier.lower()))
                )
            ).scalars().first()
            if not user or not user.is_active or not user.is_superuser:
                return False

            user_auth = (
                await session.execute(
                    select(UserAuth).where(UserAuth.user_id == user.id, UserAuth.auth_provider == "password")
                )
            ).scalars().first()

        if not user_auth or not Hash.verify(password, user_auth.password_hash):
            return False

        request.session.clear()
        request.session[SESSION_KEY] = user.id
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # Re-check the DB on every request so that deactivating or demoting
        # a user revokes their admin access immediately.
        user_id = request.session.get(SESSION_KEY)
        if user_id is None:
            return False
        user = await _get_admin_user(int(user_id))
        if user is None:
            request.session.clear()
            return False
        request.state.admin_user = user  # shown in the sidebar
        return True
