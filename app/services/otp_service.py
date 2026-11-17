import logging
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OTP, User
from app.utils.email_util import send_email
from app.utils.otp_util import generate_otp, otp_expiry
from app.utils.sms_util import send_sms
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5


class OTPService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_and_send_otp(
        self, user: User, otp_type: Literal["email", "phone", "both"] = "email"
    ) -> dict:
        """Create a fresh OTP for `user` (replacing any pending ones) and deliver it."""
        if otp_type in ("phone", "both") and not user.phone_number:
            raise HTTPException(status_code=400, detail="User has no phone number on file")

        # Replace any pending (unverified) OTPs so only the newest code is valid.
        await self.db.execute(delete(OTP).where(OTP.user_id == user.id, OTP.verified.is_(False)))

        otp_code = generate_otp()
        expires_at = otp_expiry(OTP_TTL_MINUTES)
        self.db.add(OTP(user_id=user.id, otp_code=otp_code, expires_at=expires_at))
        await self.db.commit()

        message = f"Your OTP code is: {otp_code}. It will expire in {OTP_TTL_MINUTES} minutes."
        try:
            if otp_type in ("email", "both"):
                await send_email(to=user.email, subject="Your OTP Code", body=message)
            if otp_type in ("phone", "both"):
                await send_sms(to=user.phone_number, message=message)
        except Exception as exc:
            logger.exception("Failed to deliver OTP to user %s", user.id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send OTP, please try again"
            ) from exc

        return {"message": "OTP sent successfully", "expires_at": expires_at}

    async def verify_otp(self, user_id: int, otp_code: str) -> dict:
        stmt = (
            select(OTP)
            .where(OTP.user_id == user_id, OTP.otp_code == otp_code, OTP.verified.is_(False))
            .order_by(OTP.id.desc())
        )
        otp_entry = (await self.db.execute(stmt)).scalars().first()

        if not otp_entry:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        if otp_entry.expires_at < utcnow():
            raise HTTPException(status_code=400, detail="OTP has expired")

        otp_entry.verified = True
        user = await self.db.get(User, user_id)
        if user:
            user.is_verified = True
        await self.db.commit()

        return {"message": "OTP verified successfully"}
