from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import AuthService
from app.schemas import ForgotPasswordRequest, ResetPasswordRequest, SignUpRequest, LoginRequest
from app.schemas.token import TokenResponse, RefreshTokenRequest


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/signup",
    summary="Register a new user",
    description="Create a new user account with username, email, phone number, and password. "
                "An OTP is sent to the provided contact (email or phone) for verification. "
                "New users are automatically assigned the default 'user' role if it exists.",
)
async def signup(data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.signup(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get access + refresh tokens",
    description="Authenticate with username, email, or phone number and password. "
                "Returns a short-lived access token (30 min) with roles/permissions in claims, "
                "and a long-lived refresh token (7 days). "
                "If the account is not verified, an OTP is sent instead of tokens.",
)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.login(
        username_or_email_or_phone=data.username_or_email_or_phone,
        password=data.password,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access + refresh token pair. "
                "The old refresh token is revoked (token rotation) to prevent reuse. "
                "The new access token will contain up-to-date roles and permissions.",
)
async def refresh_token(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.refresh_tokens(data.refresh_token)


@router.post(
    "/logout",
    summary="Logout and revoke refresh token",
    description="Revoke the provided refresh token so it can no longer be used. "
                "The access token will remain valid until it expires (max 30 min).",
)
async def logout(data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.logout(data.refresh_token)


@router.post(
    "/forgot-password",
    summary="Request password reset email",
    description="Send a password reset link to the registered email address. "
                "The link contains a one-time token that expires in 15 minutes.",
)
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.forgot_password(email=request.email)


@router.post(
    "/reset-password",
    summary="Reset password with token",
    description="Reset the user's password using the token received via email. "
                "The token is single-use and expires after 15 minutes.",
)
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.reset_password(
        token=request.token,
        new_password=request.new_password,
        confirm_password=request.confirm_password,
    )
