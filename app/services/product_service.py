from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse
from typing import List

class ProductService:
    @staticmethod
    def create_product(db: Session, product_data: ProductCreate, user_id: int) -> ProductResponse:
        new_product = Product(**product_data.model_dump(), user_id=user_id)
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        return new_product

    @staticmethod
    def get_product_by_id(db: Session, product_id: int, user_id: int) -> ProductResponse:
        product = db.query(Product).filter(Product.id == product_id, Product.user_id == user_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found or access denied")
        return product

    @staticmethod
    def get_all_products(db: Session, user_id: int, page: int = 1, limit: int = 10) -> List[ProductResponse]:
        if limit not in [5, 10, 20, 50]:
            raise HTTPException(status_code=400, detail="Invalid limit. Choose from 5, 10, 20, 50")

        offset = (page - 1) * limit
        products = (
            db.query(Product)
            .filter(Product.user_id == user_id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return products
