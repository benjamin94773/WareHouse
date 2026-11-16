import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Response, status
from app.database import get_db
from sqlalchemy.orm import Session
from app.modules.inventory.schemas import MovementCreate, MovementResponse, InventoryResponse
from app.modules.inventory.inventory_service import InventoryService
from app.modules.inventory.models import OutboxEventEntity

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/{product_id}", response_model=InventoryResponse)
def get_inventory(product_id: int, response: Response, db: Session = Depends(get_db)):
    data, hit = InventoryService(db).get_stock(product_id)
    response.headers["X-Cache"] = "HIT" if hit else "MISS"  # visible en curl -i y en las pruebas de carga
    return data

@router.post("/movements", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
def create_movement(payload: MovementCreate, response: Response, db: Session = Depends(get_db),
                    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    movement, created = InventoryService(db).process_movement(payload, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK  # repetición: no se reaplicó
    return movement


@router.get("/movements/by-key/{key}", response_model=MovementResponse)
def get_movement_by_key(key: str, db: Session = Depends(get_db)):
    return InventoryService(db).get_movement_by_key(key)

@router.get("/{product_id}/movements", response_model=List[MovementResponse])
def get_movements(product_id: int, db: Session = Depends(get_db)):
    service = InventoryService(db)
    return service.get_movements(product_id)

@router.get("/outbox/audit")
def get_outbox_audit(limit: int = 50, db: Session = Depends(get_db)):
    """Endpoint de auditoría: permite verificar qué eventos están PENDING o SENT en el Outbox."""
    events = db.query(OutboxEventEntity).order_by(OutboxEventEntity.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "warehouse_id": e.warehouse_id,
            "event_type": e.event_type,
            "status": e.status,
            "retry_count": e.retry_count,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            "payload": json.loads(e.payload),
        }
        for e in events
    ]
