from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas import UserResponse
from app.services import UserService
from app.utils import get_current_user
from app.utils.rbac import require_role

router = APIRouter(tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Retrieve the profile of the currently authenticated user, including their assigned roles. "
                "Requires a valid access token in the Authorization header.",
)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await UserService.get_current_user(db=db, current_user=current_user)


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all users (admin only)",
    description="Retrieve a list of all registered users with their roles. "
                "Only accessible by users with the 'admin' role.",
)
async def get_all_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("admin")),
):
    return await UserService.get_all_users(db=db)
