-- Esquema operacional de una bodega (una base PostgreSQL por bodega).
-- Se ejecuta al crear el contenedor de PostgreSQL; la API usa los mismos modelos (SQLAlchemy).

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    sku         VARCHAR NOT NULL UNIQUE,      -- identificador global entre bodegas
    name        VARCHAR NOT NULL,
    description VARCHAR,
    category    VARCHAR,
    unit        VARCHAR,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory (
    id                SERIAL PRIMARY KEY,
    product_id        INTEGER NOT NULL UNIQUE,
    warehouse_id      VARCHAR NOT NULL,
    quantity          INTEGER NOT NULL DEFAULT 0,  -- disponible
    reserved_quantity INTEGER NOT NULL DEFAULT 0,  -- retenido por reservas/transferencias
    updated_at        TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT ck_inventory_quantity CHECK (quantity >= 0),
    CONSTRAINT ck_inventory_reserved CHECK (reserved_quantity >= 0)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id           SERIAL PRIMARY KEY,
    product_id   INTEGER NOT NULL,
    warehouse_id VARCHAR NOT NULL,
    type         VARCHAR NOT NULL,  -- RECEIPT, SHIPMENT, ADJUSTMENT, RESERVATION, RELEASE, TRANSFER_OUT, TRANSFER_IN, RETURN
    quantity     INTEGER NOT NULL,
    reference    VARCHAR,
    idempotency_key VARCHAR UNIQUE,  -- reintentos de la Saga no duplican el movimiento
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_inventory_movements_product_id ON inventory_movements (product_id);

-- Transactional Outbox: eventos guardados en la misma transacción que el movimiento
CREATE TABLE IF NOT EXISTS outbox_events (
    id           VARCHAR PRIMARY KEY,  -- event_id (UUID)
    warehouse_id VARCHAR NOT NULL,
    event_type   VARCHAR NOT NULL,
    payload      VARCHAR NOT NULL,
    status       VARCHAR DEFAULT 'PENDING',  -- PENDING | SENT
    retry_count  INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now(),
    sent_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_outbox_events_status ON outbox_events (status);
