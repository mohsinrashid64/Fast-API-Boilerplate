from pydantic import BaseModel
from typing import Optional

class ProductBase(BaseModel):
    name: str
    price: float
    description: Optional[str] = None

class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    # mark all fields as optional
    name: str | None = None
    price: float | None = None
    description: str | None = None

class ProductOut(ProductBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True
