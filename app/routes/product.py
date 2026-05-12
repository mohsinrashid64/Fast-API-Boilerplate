from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database.db_config import get_db
from app.crud import product_crud
from app.schemas.product import ProductOut, ProductCreate, ProductUpdate
from app.utils.jwt import get_current_user
from app.utils.rbac import require_permission


router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "/",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
    description="Create a new product for the authenticated user. "
                "Requires 'products:write' permission.",
)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:write")),
):
    new_product = await product_crud.create(db, obj_in=product_in, user_id=current_user['id'])
    return new_product


@router.get(
    "/",
    response_model=List[ProductOut],
    summary="List your products",
    description="Retrieve a paginated list of products belonging to the authenticated user. "
                "Requires 'products:read' permission. "
                "Use 'skip' and 'limit' query parameters for pagination.",
)
async def get_products(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:read")),
):
    products = await product_crud.get_all(db, skip=skip, limit=limit, user_id=current_user['id'])
    return products


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    summary="Get a product by ID",
    description="Retrieve a single product by its ID. Only returns the product if it belongs to the authenticated user. "
                "Requires 'products:read' permission.",
)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:read")),
):
    product = await product_crud.get(db, id=product_id, user_id=current_user['id'])
    return product


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    summary="Full update a product",
    description="Replace all fields of an existing product. "
                "Requires 'products:write' permission. Only the product owner can update.",
)
async def update_product(
    product_id: int,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:write")),
):
    product = await product_crud.get(db, id=product_id, user_id=current_user['id'])
    updated_product = await product_crud.update(db, db_obj=product, obj_in=product_in)
    return updated_product


@router.patch(
    "/{product_id}",
    response_model=ProductOut,
    summary="Partially update a product",
    description="Update specific fields of an existing product (partial update). "
                "Only the fields provided in the request body will be modified. "
                "Requires 'products:write' permission. Only the product owner can update.",
)
async def partial_update_product(
    product_id: int,
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:write")),
):
    db_product = await product_crud.get(db=db, id=product_id, user_id=current_user['id'])
    updated_product = await product_crud.update(db=db, db_obj=db_product, obj_in=product_update)
    return updated_product


@router.delete(
    "/{product_id}",
    summary="Delete a product",
    description="Permanently delete a product by its ID. "
                "Requires 'products:delete' permission. Only the product owner can delete.",
)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("products:delete")),
):
    await product_crud.delete(db, id=product_id, user_id=current_user["id"])
    return {"detail": "Product deleted successfully"}
