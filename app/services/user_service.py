from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List

from app.models import User
from app.schemas.user import UserResponse


class UserService:

    @staticmethod
    async def get_current_user(db: AsyncSession, current_user: dict) -> UserResponse:
        result = await db.execute(
            select(User).where(User.id == current_user["id"]).options(selectinload(User.roles))
        )
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse.from_user(user)

    @staticmethod
    async def get_all_users(db: AsyncSession) -> List[UserResponse]:
        result = await db.execute(select(User).options(selectinload(User.roles)))
        users = result.scalars().all()
        return [UserResponse.from_user(user) for user in users]
