import asyncio
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ResetToken, User, UserAuth
from app.schemas import SignUpRequest
from app.services.otp_service import OTPService
from app.utils.crypto_util import encrypt_data
from app.utils.email_util import send_email
from app.utils.email_validator import has_mx_records
from app.utils.hashing import Hash
from app.utils.jwt import create_access_token
from app.utils.time import utc_in, utcnow

RESET_TOKEN_TTL_MINUTES = 15


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def signup(self, data: SignUpRequest) -> dict:
        # Duplicate check. Only compare phone when one was provided: comparing
        # against None would match every user without a phone number.
        conditions = [User.email == data.email, User.username == data.username]
        if data.phone_number:
            conditions.append(User.phone_number == data.phone_number)
        existing = (await self.db.execute(select(User).where(or_(*conditions)))).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="User already exists")

        # MX lookup is blocking network I/O -> run it in a thread.
        if settings.EMAIL_CHECK_MX:
            domain = data.email.split("@")[-1]
            if not await asyncio.to_thread(has_mx_records, domain):
                raise HTTPException(status_code=400, detail=f"The domain '{domain}' cannot receive email")

        user = User(username=data.username, email=data.email, phone_number=data.phone_number or None)
        user.auth.append(UserAuth(auth_provider="password", password_hash=Hash.hash(data.password)))
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        await OTPService(self.db).generate_and_send_otp(user, data.otp_type)

        return {
            "message": "User registered successfully. OTP sent to verify account.",
            "user_id": encrypt_data(user.id),
        }

    async def login(self, username_or_email_or_phone: str, password: str) -> dict:
        identifier = username_or_email_or_phone.strip()
        stmt = select(User).where(
            or_(
                User.email == identifier.lower(),
                User.username == identifier,
                User.phone_number == identifier,
            )
        )
        user = (await self.db.execute(stmt)).scalars().first()
        invalid = HTTPException(status_code=400, detail="Invalid credentials")
        if not user:
            raise invalid

        auth_stmt = select(UserAuth).where(UserAuth.user_id == user.id, UserAuth.auth_provider == "password")
        user_auth = (await self.db.execute(auth_stmt)).scalars().first()
        if not user_auth or not Hash.verify(password, user_auth.password_hash):
            raise invalid

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

        if not user.is_verified:
            otp_type = "email" if user.email else "phone"
            otp_response = await OTPService(self.db).generate_and_send_otp(user, otp_type)
            return {
                "message": "Account not verified. An OTP has been sent to your registered contact.",
                "otp_sent_to": user.email if otp_type == "email" else user.phone_number,
                "expires_at": otp_response["expires_at"],
                "user_id": encrypt_data(user.id),
            }

        token = create_access_token({"sub": str(user.id)})
        return {"access_token": token, "token_type": "bearer"}

    async def forgot_password(self, email: str) -> dict:
        # Same response whether or not the email exists, to avoid user enumeration.
        response = {"message": "If that email is registered, a password reset link has been sent"}

        user = (await self.db.execute(select(User).where(User.email == email.lower()))).scalars().first()
        if not user or not user.is_active:
            return response

        # Invalidate older tokens for this user, then issue a new one.
        await self.db.execute(delete(ResetToken).where(ResetToken.user_id == user.id))
        token = uuid.uuid4().hex
        self.db.add(ResetToken(user_id=user.id, token=token, expires_at=utc_in(minutes=RESET_TOKEN_TTL_MINUTES)))
        await self.db.commit()

        reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        body = f"""
        <p>Hello {user.username},</p>
        <p>Click the link below to reset your password:</p>
        <a href="{reset_url}">{reset_url}</a>
        <p>This link will expire in {RESET_TOKEN_TTL_MINUTES} minutes.</p>
        """
        await send_email(to=user.email, subject="Password Reset", body=body, html=True)
        return response

    async def reset_password(self, token: str, new_password: str) -> dict:
        reset_token = (await self.db.execute(select(ResetToken).where(ResetToken.token == token))).scalars().first()
        if not reset_token or reset_token.expires_at < utcnow():
            raise HTTPException(status_code=400, detail="Invalid or expired token")

        user_auth = (
            await self.db.execute(
                select(UserAuth).where(UserAuth.user_id == reset_token.user_id, UserAuth.auth_provider == "password")
            )
        ).scalars().first()
        if user_auth:
            user_auth.password_hash = Hash.hash(new_password)
        else:
            # e.g. an OAuth-only user setting a password for the first time
            self.db.add(
                UserAuth(user_id=reset_token.user_id, auth_provider="password", password_hash=Hash.hash(new_password))
            )

        await self.db.delete(reset_token)
        await self.db.commit()
        return {"message": "Password reset successfully"}
