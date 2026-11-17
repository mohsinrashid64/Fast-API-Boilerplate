from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_superuser, get_current_user
from app.database import get_db
from app.models import User
from app.schemas import UserResponse
from app.services import UserService

router = APIRouter(tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[UserResponse], dependencies=[Depends(get_current_superuser)])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all users (superusers only)."""
    return await UserService.get_all_users(db, skip=skip, limit=limit)
