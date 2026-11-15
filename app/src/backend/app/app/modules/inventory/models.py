import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from app.modules.shared.utils import schemas_utils

class InventoryEntity(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, unique=True, nullable=False)
    warehouse_id = Column(String, nullable=False)
    quantity = Column(Integer, default=0)
    reserved_quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=schemas_utils.current_utc_time, onupdate=schemas_utils.current_utc_time)

class InventoryMovementEntity(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False)
    warehouse_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String)
    created_at = Column(DateTime, default=schemas_utils.current_utc_time)

class OutboxEventEntity(Base):
    """
    Patrón Transactional Outbox:
    Garantiza que ningún evento se pierda ante caídas del broker o cortes de red.
    Se persiste en la misma transacción ACID que el movimiento de inventario.
    """
    __tablename__ = "outbox_events"

    id = Column(String, primary_key=True, index=True) # UUID único
    warehouse_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(String, nullable=False) # JSON con el contenido completo
    status = Column(String, default="PENDING", index=True) # PENDING, SENT, FAILED
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=schemas_utils.current_utc_time)
    sent_at = Column(DateTime, nullable=True)
