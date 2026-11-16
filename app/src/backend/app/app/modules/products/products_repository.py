from typing import List, Optional
from sqlalchemy.orm import Session
from app.modules.products.models import ProductEntity
from app.modules.products.schemas import ProductCreate


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, product_in: ProductCreate) -> ProductEntity:
        product = ProductEntity(**product_in.model_dump())
        self.db.add(product)
        self.db.flush()  # obtiene el id sin cerrar la transacción
        return product

    def get_by_id(self, product_id: int) -> Optional[ProductEntity]:
        return self.db.get(ProductEntity, product_id)

    def get_by_sku(self, sku: str) -> Optional[ProductEntity]:
        return self.db.query(ProductEntity).filter(ProductEntity.sku == sku).first()

    def get_all(self, skip: int, limit: int) -> List[ProductEntity]:
        return self.db.query(ProductEntity).order_by(ProductEntity.id).offset(skip).limit(limit).all()
