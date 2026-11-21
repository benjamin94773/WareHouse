#!/usr/bin/env bash
# Script de inicialización automática de datos para la bodega en Docker
# Se ejecuta en /docker-entrypoint-initdb.d/ al iniciar por primera vez el contenedor.
set -euo pipefail

WH="${WAREHOUSE_ID:-${WH_ID:-WH-001}}"

echo "[init-seed] Poblando base de datos con catálogo inicial para bodega $WH..."

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname "${POSTGRES_DB:-warehouse_db}" -v wh_id="$WH" <<-EOSQL
    -- 1. Catálogo inicial de productos
    INSERT INTO products (sku, name, description, category, unit) VALUES
        ('P-001', 'Laptop Dell Latitude 5420', 'Laptop empresarial Intel Core i5 16GB RAM 512GB SSD', 'Computo', 'UNIDAD'),
        ('P-002', 'Monitor Samsung 27 4K', 'Monitor profesional IPS UHD 3840x2160', 'Monitores', 'UNIDAD'),
        ('P-003', 'Teclado Mecanico Logitech MX', 'Teclado inalambrico retroiluminado switch brown', 'Accesorios', 'UNIDAD'),
        ('P-004', 'Mouse Ergonomico Logitech MX Master 3', 'Mouse inalambrico recargable multidispositivo', 'Accesorios', 'UNIDAD'),
        ('P-005', 'Disco SSD Samsung 1TB NVMe', 'Unidad de estado solido PCIe 4.0 M.2', 'Almacenamiento', 'UNIDAD'),
        ('P-006', 'Memoria RAM Corsair 16GB DDR4', 'Modulo de memoria 3200MHz CL16', 'Componentes', 'UNIDAD')
    ON CONFLICT (sku) DO NOTHING;

    -- 2. Inicialización de inventario para la bodega correspondiente
    INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity)
    SELECT id, :'wh_id', 100, 0
    FROM products
    WHERE sku IN ('P-001', 'P-002', 'P-003', 'P-004', 'P-005', 'P-006')
    ON CONFLICT (product_id) DO UPDATE
    SET warehouse_id = EXCLUDED.warehouse_id
    WHERE inventory.warehouse_id != EXCLUDED.warehouse_id;

    -- 3. Registro de movimientos iniciales de recepción (RECEIPT)
    INSERT INTO inventory_movements (product_id, warehouse_id, type, quantity, reference, idempotency_key)
    SELECT id, :'wh_id', 'RECEIPT', 100, 'INITIAL_SEED', 'SEED-' || :'wh_id' || '-' || sku
    FROM products
    WHERE sku IN ('P-001', 'P-002', 'P-003', 'P-004', 'P-005', 'P-006')
    ON CONFLICT (idempotency_key) DO NOTHING;
EOSQL

echo "[init-seed] Inicialización completada exitosamente para $WH."
