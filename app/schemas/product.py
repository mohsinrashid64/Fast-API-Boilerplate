from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., ge=0)
    description: str | None = None
    stock: int = Field(0, ge=0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    """All fields optional: only the fields sent are updated."""

    name: str | None = Field(None, min_length=1, max_length=255)
    price: float | None = Field(None, ge=0)
    description: str | None = None
    stock: int | None = Field(None, ge=0)


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
