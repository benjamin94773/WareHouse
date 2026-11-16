from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.modules.products.products_service import ProductService
from app.modules.products.schemas import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    return ProductService(db).create_product_with_inventory(payload)


@router.get("", response_model=List[ProductResponse])
def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return ProductService(db).list_products(skip, limit)


@router.get("/by-sku/{sku}", response_model=ProductResponse)
def get_product_by_sku(sku: str, db: Session = Depends(get_db)):
    return ProductService(db).get_by_sku(sku)


@router.get("/{id}", response_model=ProductResponse)
def get_product(id: int, db: Session = Depends(get_db)):
    return ProductService(db).get_product(id)


@router.put("/{id}", response_model=ProductResponse)
def update_product(id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    return ProductService(db).update_product(id, payload)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(id: int, db: Session = Depends(get_db)):
    ProductService(db).delete_product(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
