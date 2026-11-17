from typing import Any, Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Reusable async CRUD for SQLAlchemy models.

    If the model has a `user_id` column and a `user_id` is passed, every operation
    is scoped to that user (records owned by others behave as "not found").
    """

    def __init__(self, model: type[ModelType]):
        self.model = model

    def _scoped(self, stmt, user_id: int | None):
        if user_id is not None and hasattr(self.model, "user_id"):
            stmt = stmt.where(self.model.user_id == int(user_id))
        return stmt

    async def get(self, db: AsyncSession, id: int, user_id: int | None = None) -> ModelType:
        stmt = self._scoped(select(self.model).where(self.model.id == id), user_id)
        instance = (await db.execute(stmt)).scalar_one_or_none()
        if instance is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        return instance

    async def get_all(
        self, db: AsyncSession, skip: int = 0, limit: int = 10, user_id: int | None = None
    ) -> list[ModelType]:
        stmt = self._scoped(select(self.model), user_id).order_by(self.model.id).offset(skip).limit(limit)
        return list((await db.execute(stmt)).scalars().all())

    async def create(
        self, db: AsyncSession, obj_in: CreateSchemaType | dict, user_id: int | None = None
    ) -> ModelType:
        # Only fields the client sent: missing ones fall back to the model's column defaults.
        data = obj_in.model_dump(exclude_unset=True) if isinstance(obj_in, BaseModel) else dict(obj_in)
        if user_id is not None and hasattr(self.model, "user_id"):
            data["user_id"] = int(user_id)

        obj = self.model(**data)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def update(self, db: AsyncSession, db_obj: ModelType, obj_in: UpdateSchemaType | dict) -> ModelType:
        """Partial update: only fields present in `obj_in` are changed."""
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, id: int, user_id: int | None = None) -> dict[str, Any]:
        instance = await self.get(db, id=id, user_id=user_id)
        await db.delete(instance)
        await db.commit()
        return {"detail": "Deleted successfully"}
