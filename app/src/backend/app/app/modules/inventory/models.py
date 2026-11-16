from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String
from app.database import Base
from app.modules.shared.utils import schemas_utils


class InventoryEntity(Base):
    __tablename__ = "inventory"
    # La regla "nunca negativo" también vive en la base: ninguna ruta de código puede saltársela
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity"),
        CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, unique=True, nullable=False)
    warehouse_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)           # disponible
    reserved_quantity = Column(Integer, nullable=False, default=0)  # retenido por reservas/transferencias
    updated_at = Column(DateTime(timezone=True), default=schemas_utils.current_utc_time, onupdate=schemas_utils.current_utc_time)


class InventoryMovementEntity(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    warehouse_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String)
    # Idempotencia: el mismo Idempotency-Key nunca aplica dos veces el movimiento (p. ej. pasos de la Saga)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=schemas_utils.current_utc_time)


class OutboxEventEntity(Base):
    """
    Patrón Transactional Outbox: el evento se guarda en la misma transacción
    que el movimiento, así nunca se pierde aunque RabbitMQ esté caído.
    """
    __tablename__ = "outbox_events"

    id = Column(String, primary_key=True, index=True)  # UUID = event_id
    warehouse_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(String, nullable=False)  # JSON completo del evento
    status = Column(String, default="PENDING", index=True)  # PENDING | SENT
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=schemas_utils.current_utc_time)
    sent_at = Column(DateTime(timezone=True), nullable=True)
