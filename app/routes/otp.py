from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import OTPService
from app.schemas import OTPCreate, OTPVerify

router = APIRouter(prefix="/otp", tags=["OTP"])


@router.post(
    "/generate-manual",
    summary="Generate OTP manually (testing)",
    description="Manually generate an OTP for a given user ID. "
                "This endpoint is intended for testing and development only.",
)
def generate_manual_otp(user_id: int, db: Session = Depends(get_db)):
    otp_service = OTPService(db)
    contact = "example@test.com"
    contact_type = "email"
    return otp_service.generate_and_send_otp(user_id=user_id, contact=contact, contact_type=contact_type)


@router.post(
    "/generate",
    summary="Generate and send OTP",
    description="Generate a 6-digit OTP and send it to the user's contact (email or phone). "
                "The OTP expires after 5 minutes.",
)
def generate_otp(data: OTPCreate, db: Session = Depends(get_db)):
    otp_service = OTPService(db)
    return otp_service.generate_and_send_otp(user_id=data.user_id, contact=data.contact, contact_type=data.contact_type)


@router.post(
    "/verify",
    summary="Verify OTP code",
    description="Verify a 6-digit OTP code for a user. On success, the user's account is marked as verified. "
                "The user_id should be the encrypted user ID returned during signup.",
)
async def verify_otp(data: OTPVerify, db: Session = Depends(get_db)):
    otp_service = OTPService(db)
    return await otp_service.verify_otp(encrypted_user_id=data.user_id, otp_code=data.otp_code)
