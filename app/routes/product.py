from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.crud import product_crud
from app.database import get_db
from app.models import User
from app.schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])

# Every endpoint is scoped to the current user: other users' products are 404.


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await product_crud.create(db, obj_in=product_in, user_id=current_user.id)


@router.get("/", response_model=list[ProductOut])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await product_crud.get_all(db, skip=skip, limit=limit, user_id=current_user.id)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await product_crud.get(db, id=product_id, user_id=current_user.id)


@router.put("/{product_id}", response_model=ProductOut)
async def replace_product(
    product_id: int,
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full update: all fields are required."""
    product = await product_crud.get(db, id=product_id, user_id=current_user.id)
    return await product_crud.update(db, db_obj=product, obj_in=product_in.model_dump())


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partial update: only the fields sent are changed."""
    product = await product_crud.get(db, id=product_id, user_id=current_user.id)
    return await product_crud.update(db, db_obj=product, obj_in=product_in)


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await product_crud.delete(db, id=product_id, user_id=current_user.id)
    return {"detail": "Product deleted successfully"}
