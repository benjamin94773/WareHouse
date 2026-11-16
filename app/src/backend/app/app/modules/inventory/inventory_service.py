import uuid
import json
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app import cache
from app.config import settings
from app.modules.inventory.schemas import InventoryResponse, MovementCreate
from app.modules.inventory.inventory_repository import InventoryRepository

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = InventoryRepository(db)

    def initialize_stock(self, product_id: int) -> None:
        self.repo.initialize_inventory(product_id)

    def get_stock(self, product_id: int):
        """Cache Aside: Redis -> (miss) PostgreSQL -> Redis. Devuelve (datos, hit)."""
        key = cache.inventory_key(product_id)
        cached = cache.get_json(key)
        if cached:
            return cached, True
        inventory = self.repo.get_by_product(product_id)
        if not inventory:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventario no encontrado")
        data = InventoryResponse.model_validate(inventory).model_dump(mode="json")
        cache.set_json(key, data)
        return data, False

    def process_movement(self, movement_in: MovementCreate):
        try:
            # 1. Bloqueo pesimista de la fila: dos salidas concurrentes se serializan aquí
            inventory = self.repo.get_by_product_for_update(movement_in.product_id)
            if not inventory:
                # La fila se crea junto con el producto: si no existe, el producto no existe
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Producto {movement_in.product_id} no existe en {settings.WAREHOUSE_ID}")

            new_qty = inventory.quantity
            new_reserved = inventory.reserved_quantity
            m_type = movement_in.type.value
            qty = movement_in.quantity

            # 2. Reglas de negocio: quantity = disponible, reserved_quantity = retenido
            if m_type in ("RECEIPT", "TRANSFER_IN", "RETURN"):
                new_qty += qty
            elif m_type in ("SHIPMENT", "TRANSFER_OUT"):
                if new_qty < qty:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Stock insuficiente. Disponible: {new_qty}, Requerido: {qty}")
                new_qty -= qty
            elif m_type == "ADJUSTMENT":
                if new_qty + qty < 0:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El ajuste dejaría el inventario negativo ({new_qty} {qty:+d})")
                new_qty += qty
            elif m_type == "RESERVATION":
                if new_qty < qty:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stock insuficiente para reservar")
                new_qty -= qty
                new_reserved += qty
            elif m_type == "RELEASE":
                if new_reserved < qty:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Liberación excede reserva existente")
                new_reserved -= qty
                new_qty += qty

            # 3. Aplicar mutación y registrar movimiento
            self.repo.update_stock(inventory, new_qty, new_reserved)
            movement = self.repo.register_movement(movement_in.product_id, m_type, qty, movement_in.reference)

            # 4. PATRÓN TRANSACTIONAL OUTBOX:
            # Registrar el evento en la misma transacción ACID de PostgreSQL.
            # Si el broker RabbitMQ está caído, este evento permanece seguro en la base de datos local.
            event_id = str(uuid.uuid4())
            event_payload = {
                "event_id": event_id,
                "warehouse_id": settings.WAREHOUSE_ID,
                "event_type": m_type,
                "product_id": movement_in.product_id,
                "quantity": qty,
                "reference": movement_in.reference,
                "balance_after": new_qty,
                "timestamp": datetime.utcnow().isoformat()
            }

            self.repo.register_outbox_event(
                event_id=event_id,
                event_type=m_type,
                payload_str=json.dumps(event_payload)
            )

            # 5. Confirmación atómica de ambas operaciones
            self.db.commit()
            # Invalidación síncrona después del commit: la próxima lectura trae el valor nuevo
            cache.delete(cache.inventory_key(movement_in.product_id))
            return movement
        except Exception:
            # ROLLBACK: inventario, movimiento y evento se descartan juntos
            self.db.rollback()
            raise

    def get_movements(self, product_id: int):
        return self.repo.get_movements_by_product(product_id)

    def get_outbox_events(self, limit: int = 50):
        return self.repo.get_pending_outbox_events(limit)
