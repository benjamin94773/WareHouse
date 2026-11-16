"""Base de la central: read model (CQRS), idempotencia, estado de bodegas, sagas y jobs."""
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

engine = create_engine(os.getenv("CENTRAL_DATABASE_URL", "sqlite:///./central.db"), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now():
    return datetime.now(timezone.utc)


def aware(dt):
    """SQLite devuelve datetimes sin zona; se normalizan a UTC para comparar."""
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


class InventoryView(Base):
    """Read model: último balance conocido de cada sku en cada bodega."""
    __tablename__ = "inventory_view"
    warehouse_id = Column(String, primary_key=True)
    sku = Column(String, primary_key=True)
    product_id = Column(Integer)
    product_name = Column(String)
    quantity = Column(Integer, nullable=False)
    reserved_quantity = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)  # movement_id del último evento aplicado
    updated_at = Column(DateTime(timezone=True))  # occurred_at del evento


class ProcessedEvent(Base):
    """Idempotencia persistente: (event_id, consumer) procesado una sola vez."""
    __tablename__ = "processed_events"
    event_id = Column(String, primary_key=True)
    consumer = Column(String, primary_key=True)
    processed_at = Column(DateTime(timezone=True), default=now)


class EventLog(Base):
    """Histórico de movimientos recibidos; fuente del batch diario y del feed del dashboard."""
    __tablename__ = "event_log"
    event_id = Column(String, primary_key=True)
    warehouse_id = Column(String, index=True, nullable=False)
    sku = Column(String, nullable=False)
    movement_type = Column(String, nullable=False)
    movement_quantity = Column(Integer, nullable=False)
    reference = Column(String)
    correlation_id = Column(String)
    occurred_at = Column(DateTime(timezone=True), index=True)
    received_at = Column(DateTime(timezone=True), default=now)
    payload = Column(JSON)


class WarehouseStatus(Base):
    __tablename__ = "warehouse_status"
    warehouse_id = Column(String, primary_key=True)
    healthy = Column(Boolean, default=False)
    last_health_ok_at = Column(DateTime(timezone=True))
    last_event_at = Column(DateTime(timezone=True))
    last_error = Column(Text)


class Transfer(Base):
    """Estado persistido de la Saga: el worker puede caer y retomar desde el último paso confirmado."""
    __tablename__ = "transfers"
    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, index=True)
    error = Column(Text)
    simulate_failure = Column(String)  # before_reserve | after_reserve (experimentos)
    step_delay = Column(Integer, default=0)  # segundos entre pasos, para reiniciar el worker a mitad
    correlation_id = Column(String)
    history = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
