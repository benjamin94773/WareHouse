from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.inventory.inventory_service import InventoryService
from app.modules.products.products_repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.product_repo = ProductRepository(db)
        self.inventory_service = InventoryService(db)

    def create_product_with_inventory(self, product_in: ProductCreate):
        """Producto + fila de inventario en cero, en una sola transacción."""
        try:
            product = self.product_repo.create(product_in)
            self.inventory_service.initialize_stock(product.id)
            self.db.commit()
            return product
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe un producto con sku '{product_in.sku}'")

    def get_product(self, product_id: int):
        product = self.product_repo.get_by_id(product_id)
        if not product:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
        return product

    def get_by_sku(self, sku: str):
        product = self.product_repo.get_by_sku(sku)
        if not product:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
        return product

    def list_products(self, skip: int, limit: int):
        return self.product_repo.get_all(skip, limit)

    def update_product(self, product_id: int, product_in: ProductUpdate):
        product = self.get_product(product_id)
        for field, value in product_in.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        self.db.commit()
        return product

    def delete_product(self, product_id: int):
        """Solo se elimina si no tiene stock ni reservas, para no perder inventario."""
        product = self.get_product(product_id)
        inventory = self.inventory_service.repo.get_by_product_for_update(product_id)
        if inventory and (inventory.quantity or inventory.reserved_quantity):
            raise HTTPException(status.HTTP_409_CONFLICT, "No se puede eliminar un producto con stock o reservas")
        if inventory:
            self.db.delete(inventory)
        self.db.delete(product)
        self.db.commit()
