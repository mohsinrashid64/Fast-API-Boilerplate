from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import OTPCreate, OTPVerify
from app.services import OTPService
from app.utils.crypto_util import decrypt_data

router = APIRouter(prefix="/otp", tags=["OTP"])


def _decrypt_user_id(encrypted_user_id: str) -> int:
    try:
        return decrypt_data(encrypted_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")


@router.post("/generate")
async def generate_otp(data: OTPCreate, db: AsyncSession = Depends(get_db)):
    """(Re)send an OTP to the user identified by the encrypted `user_id`."""
    user = await db.get(User, _decrypt_user_id(data.user_id))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Account is already verified")
    return await OTPService(db).generate_and_send_otp(user, data.otp_type)


@router.post("/verify")
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    return await OTPService(db).verify_otp(user_id=_decrypt_user_id(data.user_id), otp_code=data.otp_code)
