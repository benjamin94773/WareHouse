from typing import List
from fastapi import APIRouter, Depends, Response, status
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
def create_movement(payload: MovementCreate, db: Session = Depends(get_db)):
    service = InventoryService(db)
    return service.process_movement(payload)

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
            "sent_at": e.sent_at.isoformat() if e.sent_at else None
        }
        for e in events
    ]
