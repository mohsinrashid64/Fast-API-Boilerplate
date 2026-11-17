from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserService:
    @staticmethod
    async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[User]:
        result = await db.execute(select(User).order_by(User.id).offset(skip).limit(limit))
        return list(result.scalars().all())
