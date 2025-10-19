from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import AuthService
from app.schemas import ForgotPasswordRequest, ResetPasswordRequest, SignUpRequest, LoginRequest


router = APIRouter(prefix="/auth", tags=["Auth"])



@router.post("/signup")
async def signup(data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.signup(data)


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    return await auth_service.login(
        username_or_email_or_phone=data.username_or_email_or_phone,
        password=data.password
    )


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    return AuthService(db).forgot_password(email=request.email)


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    return AuthService(db).reset_password(
        token=request.token,
        new_password=request.new_password,
        confirm_password=request.confirm_password
    )
