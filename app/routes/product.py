from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database.db_config import get_db
from app.crud import product_crud
from app.schemas.product import ProductOut, ProductCreate, ProductUpdate
from app.utils.jwt import get_current_user



router = APIRouter(prefix="/products", tags=["Products"])


# ✅ Create product
@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    new_product = await product_crud.create(db, obj_in=product_in, user_id=current_user['id'])
    return new_product


# ✅ Get all products (admin view or general list)
@router.get("/", response_model=List[ProductOut])
async def get_products(
    skip: int = 0, limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    products = await product_crud.get_all(db, skip=skip, limit=limit, user_id=current_user['id'])
    return products



# ✅ Get product by ID
@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    product = await product_crud.get(db, id=product_id, user_id=current_user['id'])
    return product


# ✅ Update product
@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    product = await product_crud.get(db, id=product_id)
    updated_product = await product_crud.update(db, db_obj=product, obj_in=product_in)
    return updated_product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Partially update a product.
    Only the product owner can update their own product.
    """
    db_product = await product_crud.get(db=db, id=product_id)
    updated_product = await product_crud.update(db=db, db_obj=db_product, obj_in=product_update)
    return updated_product


# ✅ Delete product
@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    await product_crud.delete(db, id=product_id, user_id=current_user["id"])
    return {"detail": "Product deleted successfully"}