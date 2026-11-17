from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OTPCreate(BaseModel):
    """Request a (new) OTP for a user, e.g. a "resend code" button."""

    user_id: str = Field(..., description="Encrypted user id returned by signup/login")
    otp_type: Literal["email", "phone", "both"] = "email"


class OTPVerify(BaseModel):
    user_id: str = Field(..., description="Encrypted user id returned by signup/login")
    otp_code: str = Field(..., min_length=6, max_length=6, description="The OTP to verify")


class OTPResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    expires_at: datetime
    verified: bool
