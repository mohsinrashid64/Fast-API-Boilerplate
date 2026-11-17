from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, SignUpRequest
from app.services import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", status_code=201)
async def signup(data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).signup(data)


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).login(
        username_or_email_or_phone=data.username_or_email_or_phone,
        password=data.password,
    )


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).forgot_password(email=request.email)


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).reset_password(token=request.token, new_password=request.new_password)
