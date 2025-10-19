from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas import UserResponse
from app.services import UserService
from app.utils import get_current_user

router = APIRouter()

# Route to get user details (requires token)
@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await UserService.get_current_user(db=db, current_user=current_user)


@router.get("/users", response_model=List[UserResponse])
async def get_all_users(db: AsyncSession = Depends(get_db)):
    return await UserService.get_all_users(db=db)