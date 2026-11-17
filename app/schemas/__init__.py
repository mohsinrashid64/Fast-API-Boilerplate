from .auth import (
    ForgotPasswordRequest,
    GoogleAuthCallback,
    LoginRequest,
    ResetPasswordRequest,
    SignUpRequest,
    TokenResponse,
)
from .otp import OTPCreate, OTPResponse, OTPVerify
from .product import ProductBase, ProductCreate, ProductOut, ProductUpdate
from .user import UserBase, UserResponse

__all__ = [
    # auth
    "SignUpRequest",
    "LoginRequest",
    "TokenResponse",
    "GoogleAuthCallback",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    # otp
    "OTPCreate",
    "OTPVerify",
    "OTPResponse",
    # user
    "UserBase",
    "UserResponse",
    # product
    "ProductBase",
    "ProductCreate",
    "ProductUpdate",
    "ProductOut",
]
