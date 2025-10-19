from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models import User, OTP
from app.utils.otp_util import generate_otp, otp_expiry
from app.utils.email_util import send_email
from app.utils.sms_util import send_sms
from app.utils.crypto_util import decrypt_data


class OTPService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_and_send_otp(self, user_id: int, contact: str, contact_type: str = "email"):
        print("contact_type:", contact_type)

        # Step 1: Validate input
        if not user_id or not isinstance(user_id, int):
            raise HTTPException(status_code=400, detail="Invalid user_id")
        if not contact or not isinstance(contact, str):
            raise HTTPException(status_code=400, detail="Invalid contact information")
        if contact_type not in ["email", "phone"]:
            raise HTTPException(status_code=400, detail="Invalid contact type")

        # Step 2: Check for existing unexpired OTP for the user
        stmt = (
            select(OTP)
            .where(OTP.user_id == user_id)
            .where(OTP.expires_at > datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        existing_otp = result.scalar_one_or_none()

        if existing_otp:
            raise HTTPException(status_code=400, detail="An unexpired OTP already exists for this user")

        # Step 3: Generate OTP and expiry time
        otp_code = generate_otp()
        expires_at = otp_expiry()

        # Step 4: Add OTP to the database
        otp_entry = OTP(user_id=user_id, otp_code=otp_code, expires_at=expires_at)
        self.db.add(otp_entry)

        try:
            await self.db.commit()
            await self.db.refresh(otp_entry)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

        # Step 5: Send OTP (non-blocking if possible)
        try:
            if contact_type == "email":
                # If send_email is blocking, run it in thread pool
                await send_email(
                    to=contact,
                    subject="Your OTP Code",
                    body=f"Your OTP code is: {otp_code}. It will expire in 5 minutes.",
                )
            elif contact_type == "phone":
                await send_sms(
                    to=contact,
                    message=f"Your OTP code is: {otp_code}. It will expire in 5 minutes.",
                )
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to send OTP: {str(e)}")

        return {"message": "OTP sent successfully", "expires_at": expires_at}

###

    async def verify_otp(self, encrypted_user_id: str, otp_code: str):
        # Step 1: Decrypt and validate user ID
        try:
            user_id = int(decrypt_data(encrypted_user_id))
            print("USER ID", user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user ID")

        # Step 2: Find OTP entry
        stmt = select(OTP).where(OTP.user_id == user_id, OTP.otp_code == otp_code)
        result = await self.db.execute(stmt)
        otp_entry = result.scalar_one_or_none()

        if not otp_entry:
            raise HTTPException(status_code=400, detail="Invalid OTP")

        # Step 3: Check expiration
        if otp_entry.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="OTP has expired")

        # Step 4: Mark OTP as verified
        otp_entry.verified = True
        self.db.add(otp_entry)

        # Step 5: Mark user as verified (if exists)
        user_stmt = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if user:
            user.is_verified = True
            self.db.add(user)

        # Step 6: Commit all updates safely
        try:
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

        return {"message": "OTP verified successfully"}