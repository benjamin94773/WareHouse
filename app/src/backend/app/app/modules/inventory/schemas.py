from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class MovementType(str, Enum):
    RECEIPT = "RECEIPT"            # entrada de proveedor (+)
    SHIPMENT = "SHIPMENT"          # salida a cliente (-)
    ADJUSTMENT = "ADJUSTMENT"      # ajuste de conteo (+/-)
    RESERVATION = "RESERVATION"    # disponible -> reservado
    RELEASE = "RELEASE"            # reservado -> disponible (compensación)
    TRANSFER_OUT = "TRANSFER_OUT"  # sale lo reservado hacia otra bodega
    TRANSFER_IN = "TRANSFER_IN"    # llega desde otra bodega (+)
    RETURN = "RETURN"              # devolución de cliente (+)


class MovementCreate(BaseModel):
    product_id: int
    type: MovementType
    quantity: int = Field(..., description="> 0; solo ADJUSTMENT admite valores negativos")
    reference: Optional[str] = None

    @model_validator(mode="after")
    def check_quantity(self):
        if self.quantity == 0 or (self.quantity < 0 and self.type != MovementType.ADJUSTMENT):
            raise ValueError("quantity debe ser > 0 (ADJUSTMENT admite negativos, pero no 0)")
        return self


class MovementResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: str
    type: str
    quantity: int
    reference: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryResponse(BaseModel):
    product_id: int
    warehouse_id: str
    quantity: int
    reserved_quantity: int
    updated_at: datetime

    class Config:
        from_attributes = True
