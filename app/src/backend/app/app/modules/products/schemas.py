from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str = Field(..., min_length=1)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = Field(None, min_length=1)


class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    unit: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
