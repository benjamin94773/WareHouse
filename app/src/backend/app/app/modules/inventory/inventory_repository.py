from typing import List, Optional
import datetime
from app.config import settings
from sqlalchemy.orm import Session
from app.modules.inventory.models import InventoryEntity, InventoryMovementEntity, OutboxEventEntity
from app.modules.shared.utils import schemas_utils

class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def initialize_inventory(self, product_id: int) -> InventoryEntity:
        inventory = InventoryEntity(
            product_id=product_id,
            warehouse_id=settings.WAREHOUSE_ID,
            quantity=0,
            reserved_quantity=0
        )
        self.db.add(inventory)
        return inventory

    def get_by_product_for_update(self, product_id: int) -> Optional[InventoryEntity]:
        return self.db.query(InventoryEntity).filter(
            InventoryEntity.product_id == product_id,
            InventoryEntity.warehouse_id == settings.WAREHOUSE_ID
        ).with_for_update().first()

    def get_by_product(self, product_id: int) -> Optional[InventoryEntity]:
        return self.db.query(InventoryEntity).filter(
            InventoryEntity.product_id == product_id,
            InventoryEntity.warehouse_id == settings.WAREHOUSE_ID
        ).first()

    def update_stock(self, inventory: InventoryEntity, quantity: int, reserved_quantity: int) -> None:
        inventory.quantity = quantity
        inventory.reserved_quantity = reserved_quantity
        self.db.add(inventory)

    def register_movement(self, product_id: int, m_type: str, qty: int, ref: Optional[str]) -> InventoryMovementEntity:
        movement = InventoryMovementEntity(
            product_id=product_id,
            warehouse_id=settings.WAREHOUSE_ID,
            type=m_type,
            quantity=qty,
            reference=ref
        )
        self.db.add(movement)
        return movement

    def get_movements_by_product(self, product_id: int) -> List[InventoryMovementEntity]:
        return self.db.query(InventoryMovementEntity).filter(
            InventoryMovementEntity.product_id == product_id,
            InventoryMovementEntity.warehouse_id == settings.WAREHOUSE_ID
        ).order_by(InventoryMovementEntity.id).all()

    # ==========================================================================
    # Operaciones del Patrón Outbox
    # ==========================================================================

    def register_outbox_event(self, event_id: str, event_type: str, payload_str: str) -> OutboxEventEntity:
        event = OutboxEventEntity(
            id=event_id,
            warehouse_id=settings.WAREHOUSE_ID,
            event_type=event_type,
            payload=payload_str,
            status="PENDING",
            retry_count=0
        )
        self.db.add(event)
        return event

    def get_pending_outbox_events(self, limit: int = 50) -> List[OutboxEventEntity]:
        return self.db.query(OutboxEventEntity).filter(
            OutboxEventEntity.status == "PENDING"
        ).order_by(OutboxEventEntity.created_at.asc()).limit(limit).all()

    def mark_outbox_event_sent(self, event_id: str) -> None:
        event = self.db.query(OutboxEventEntity).filter(OutboxEventEntity.id == event_id).first()
        if event:
            event.status = "SENT"
            event.sent_at = schemas_utils.current_utc_time()
            self.db.add(event)
            self.db.commit()

    def increment_outbox_retry(self, event_id: str) -> None:
        event = self.db.query(OutboxEventEntity).filter(OutboxEventEntity.id == event_id).first()
        if event:
            event.retry_count += 1
            self.db.add(event)
            self.db.commit()
