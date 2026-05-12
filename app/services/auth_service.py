from datetime import datetime, timedelta
import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import User, UserAuth, ResetToken, Role, RefreshToken
from app.services.otp_service import OTPService
from app.utils.email_util import send_email
from app.utils.hashing import Hash
from app.utils.jwt import (
    create_access_token, create_refresh_token,
    verify_refresh_token, REFRESH_TOKEN_EXPIRE_MINUTES,
)
from app.utils.crypto_util import encrypt_data


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── helpers ───

    async def _get_user_roles_and_permissions(self, user: User):
        """Extract role names and permission names from a user's roles."""
        role_names = [r.name for r in user.roles] if user.roles else []
        permission_names = set()
        for role in (user.roles or []):
            for perm in role.permissions:
                permission_names.add(perm.name)
        return role_names, sorted(permission_names)

    async def _generate_tokens(self, user: User) -> dict:
        """Create access + refresh tokens and persist the refresh token."""
        role_names, permission_names = await self._get_user_roles_and_permissions(user)

        access_token = create_access_token(
            data={"sub": str(user.id)},
            roles=role_names,
            permissions=permission_names,
        )
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # Persist refresh token
        expires_at = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
        db_token = RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires_at)
        self.db.add(db_token)
        await self.db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "roles": role_names,
            "permissions": permission_names,
        }

    async def _get_user_with_roles(self, user_id: int) -> User:
        """Fetch a user with roles eagerly loaded."""
        stmt = select(User).where(User.id == user_id).options(selectinload(User.roles))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ─── signup ───

    async def signup(self, data):
        # Check for duplicate user
        query = select(User).where(
            (User.email == data.email) |
            (User.username == data.username) |
            (User.phone_number == data.phone_number)
        )
        result = await self.db.execute(query)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")

        if data.password != data.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        if data.otp_type not in ["email", "phone", "both"]:
            raise HTTPException(status_code=400, detail="Invalid otp_type")

        if data.otp_type == "email" and not data.email:
            raise HTTPException(status_code=400, detail="Email is required for email otp_type")
        elif data.otp_type == "phone" and not data.phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required for phone otp_type")

        hashed_password = Hash.hash(data.password)

        # Create new user
        user = User(
            username=data.username,
            email=data.email,
            phone_number=data.phone_number if data.phone_number else None,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # Create user auth entry
        user_auth = UserAuth(
            user_id=user.id,
            auth_provider="password",
            password_hash=hashed_password,
        )
        self.db.add(user_auth)

        # Assign default "user" role if it exists
        role_result = await self.db.execute(select(Role).where(Role.name == "user"))
        default_role = role_result.scalar_one_or_none()
        if default_role:
            user.roles.append(default_role)

        await self.db.commit()

        # Generate and send OTP
        otp_service = OTPService(self.db)
        contact_type = data.otp_type
        contact = data.email if contact_type == "email" else data.phone_number

        await otp_service.generate_and_send_otp(user_id=user.id, contact=contact, contact_type=contact_type)

        encrypted_user_id = encrypt_data(str(user.id))

        return {
            "message": "User registered successfully. OTP sent to verify account.",
            "user_id": encrypted_user_id,
        }

    # ─── login ───

    async def login(self, username_or_email_or_phone: str, password: str):
        # Get user (with roles loaded)
        stmt = (
            select(User)
            .where(
                (User.email == username_or_email_or_phone) |
                (User.username == username_or_email_or_phone) |
                (User.phone_number == username_or_email_or_phone)
            )
            .options(selectinload(User.roles))
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        # Verify password
        auth_stmt = select(UserAuth).where(
            (UserAuth.user_id == user.id) &
            (UserAuth.auth_provider == "password")
        )
        auth_result = await self.db.execute(auth_stmt)
        user_auth = auth_result.scalar_one_or_none()

        if not user_auth or not Hash.verify(password, user_auth.password_hash):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        # If not verified, send OTP
        if not user.is_verified:
            otp_service = OTPService(self.db)
            contact = user.email if user.email else user.phone_number
            contact_type = "email" if user.email else "phone"

            otp_response = await otp_service.generate_and_send_otp(
                user_id=user.id, contact=contact, contact_type=contact_type,
            )
            encrypted_user_id = encrypt_data(str(user.id))

            return {
                "message": "Account not verified. An OTP has been sent to your registered contact.",
                "otp_sent_to": contact,
                "expires_at": otp_response["expires_at"],
                "user_id": encrypted_user_id,
            }

        # Generate access + refresh tokens
        return await self._generate_tokens(user)

    # ─── refresh token ───

    async def refresh_tokens(self, refresh_token_str: str):
        """Validate a refresh token, revoke it, and issue a new token pair (rotation)."""
        payload = verify_refresh_token(refresh_token_str)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Check token exists in DB and is not revoked
        stmt = select(RefreshToken).where(
            (RefreshToken.token == refresh_token_str) &
            (RefreshToken.revoked == False)
        )
        result = await self.db.execute(stmt)
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(status_code=401, detail="Refresh token is invalid or has been revoked")

        # Revoke the old refresh token (rotation)
        db_token.revoked = True
        await self.db.commit()

        # Issue new tokens
        user = await self._get_user_with_roles(int(user_id))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return await self._generate_tokens(user)

    # ─── logout (revoke refresh token) ───

    async def logout(self, refresh_token_str: str):
        """Revoke a refresh token on logout."""
        stmt = select(RefreshToken).where(RefreshToken.token == refresh_token_str)
        result = await self.db.execute(stmt)
        db_token = result.scalar_one_or_none()

        if db_token:
            db_token.revoked = True
            await self.db.commit()

        return {"message": "Logged out successfully"}

    # ─── forgot password ───

    async def forgot_password(self, email: str):
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        reset_token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        new_reset_token = ResetToken(user_id=user.id, token=reset_token, expires_at=expires_at)
        self.db.add(new_reset_token)
        await self.db.commit()

        reset_url = f"http://localhost:8000/auth/reset-password?token={reset_token}"
        email_content = f"""
        <p>Hello {user.username},</p>
        <p>Click the link below to reset your password:</p>
        <a href="{reset_url}">{reset_url}</a>
        <p>This link will expire in 15 minutes.</p>
        """
        send_email(to=user.email, subject="Password Reset", body=email_content)

        return {"message": "Password reset email sent"}

    # ─── reset password ───

    async def reset_password(self, token: str, new_password: str, confirm_password: str):
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        result = await self.db.execute(select(ResetToken).where(ResetToken.token == token))
        reset_token = result.scalar_one_or_none()

        if not reset_token or reset_token.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Invalid or expired token")

        auth_result = await self.db.execute(
            select(UserAuth).where(UserAuth.user_id == reset_token.user_id)
        )
        user_auth = auth_result.scalar_one_or_none()

        if not user_auth:
            raise HTTPException(status_code=404, detail="User authentication record not found")

        user_auth.password_hash = Hash.hash(new_password)
        self.db.add(user_auth)
        await self.db.delete(reset_token)
        await self.db.commit()

        return {"message": "Password reset successfully"}
