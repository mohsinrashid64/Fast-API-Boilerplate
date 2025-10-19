from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.models import User
from app.schemas.user import UserResponse

class UserService:

    @staticmethod
    async def get_current_user(db: AsyncSession, current_user: dict) -> UserResponse:
        result = await db.execute(select(User).where(User.id == current_user["id"]))
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone_number=user.phone_number,
            is_verified=user.is_verified,
        )

    @staticmethod
    async def get_all_users(db: AsyncSession) -> List[UserResponse]:
        result = await db.execute(select(User))
        users = result.scalars().all()
        return [UserResponse.model_validate(user) for user in users]
