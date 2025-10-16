from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.db_config import get_db
from app.crud import product_crud
from app.schemas.product import ProductResponse, ProductCreate
from app.utils.jwt import get_current_user

router = APIRouter(prefix="/products", tags=["Products"])

# Get product by ID
@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    product = product_crud.get(db=db, id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# Get all products with pagination
@router.get("/", response_model=List[ProductResponse])
def get_products(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    skip = (page - 1) * limit
    return product_crud.get_all(db=db, skip=skip, limit=limit)

# Get only product names
@router.get("/names", response_model=List[str])
def get_product_names(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return product_crud.get_names_only(db=db)

# Create product
@router.post("/", response_model=ProductResponse)
def create_product(product_in: ProductCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return product_crud.create(db=db, obj_in=product_in)
