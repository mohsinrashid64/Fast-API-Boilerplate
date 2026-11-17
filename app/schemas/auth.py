from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.utils.email_validator import validate_email_domain

OTPChannel = Literal["email", "phone", "both"]


class SignUpRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    phone_number: str | None = Field(None, max_length=15, description="E.164 format, e.g. +1234567890")
    password: str = Field(..., min_length=8, max_length=72)
    confirm_password: str
    otp_type: OTPChannel = "email"

    @field_validator("email")
    @classmethod
    def email_from_known_provider(cls, value: str) -> str:
        validate_email_domain(value)  # raises ValueError -> 422
        return value.lower()

    @model_validator(mode="after")
    def check_consistency(self) -> "SignUpRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if self.otp_type in ("phone", "both") and not self.phone_number:
            raise ValueError("phone_number is required when otp_type is 'phone' or 'both'")
        return self


class LoginRequest(BaseModel):
    username_or_email_or_phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleAuthCallback(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=72)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
