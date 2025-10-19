from typing import TypeVar, Generic, Type, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from fastapi import HTTPException, status

# Type variables for generic CRUD base
ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    A reusable, async CRUD base class that supports user-based filtering.
    It handles all major CRUD operations for SQLAlchemy models.
    """

    def __init__(self, model: Type[ModelType]):
        self.model = model


    # --------------------- GET ONE ---------------------
    async def get(self, db: AsyncSession, id: int, user_id: Optional[int] = None) -> Optional[ModelType]:
        """
        Get a single record by ID.
        If user_id is provided, ensure the record belongs to that user.
        """
        stmt = select(self.model).where(self.model.id == id)

        if hasattr(self.model, "user_id") and user_id is not None:
            stmt = stmt.where(self.model.user_id == user_id)

        result = await db.execute(stmt)
        instance = result.scalar_one_or_none()

        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        return instance

    # --------------------- GET ALL ---------------------
    async def get_all(
        self, db: AsyncSession, skip: int = 0, limit: int = 10, user_id: Optional[int] = None
    ) -> List[ModelType]:
        """
        Get all records with optional pagination and user filtering.
        """
        stmt = select(self.model).offset(skip).limit(limit)
        print('USER ID:', user_id)

        if hasattr(self.model, "user_id") and user_id is not None:
            stmt = stmt.where(self.model.user_id == user_id)

        result = await db.execute(stmt)
        return result.scalars().all()

    # --------------------- CREATE ---------------------
    async def create(
        self, db: AsyncSession, obj_in: CreateSchemaType | dict, user_id: Optional[int] = None
    ) -> ModelType:
        """
        Create a new record.
        Automatically attaches user_id if model supports it.
        """
        data = obj_in.dict() if hasattr(obj_in, "dict") else dict(obj_in)

        if hasattr(self.model, "user_id") and user_id is not None:
            data["user_id"] = user_id

        obj = self.model(**data)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    # --------------------- UPDATE ---------------------
    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict
    ) -> ModelType:
        """
        Updates a database object.
        Accepts either a Pydantic schema or a raw dict.
        Only updates fields provided (partial update).
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            # Exclude unset fields if it's a Pydantic model
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    # --------------------- DELETE ---------------------
    async def delete(self, db: AsyncSession, id: int, user_id: Optional[int] = None) -> dict[str, Any]:
        """
        Delete a record by ID, with optional ownership enforcement if model has 'user_id'.
        """
        # Get the record
        stmt = select(self.model).where(self.model.id == id)
        result = await db.execute(stmt)
        instance = result.scalar_one_or_none()


        # Record not found
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        # 🚨 Ownership check
        if hasattr(instance, "user_id") and user_id is not None:
            if int(instance.user_id) != int(user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to delete this item"
                )

        await db.delete(instance)
        await db.commit()
        return {"detail": "Deleted successfully"}

    # --------------------- GET BY USER ---------------------
    async def get_by_user(
        self, db: AsyncSession, user_id: int, skip: int = 0, limit: int = 10
    ) -> List[ModelType]:
        """
        Get all items for a specific user (one-to-many relationship).
        """
        if not hasattr(self.model, "user_id"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model does not support user relation")

        stmt = select(self.model).where(self.model.user_id == user_id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()


