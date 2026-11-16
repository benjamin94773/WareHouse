-- Fase 6: idempotencia de movimientos (pasos de la Saga)
ALTER TABLE inventory_movements ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR;
CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_movements_idempotency_key ON inventory_movements (idempotency_key);
