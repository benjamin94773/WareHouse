-- Datos iniciales de prueba para la bodega (seed.sql)
-- Cumple con el Entregable 4 (Persistencia: schema.sql, seed.sql, migrations/)
-- Nota: Para ejecución manual o en entornos de prueba. En Docker, init-seed.sh
-- inyecta dinámicamente el WAREHOUSE_ID correspondiente a cada contenedor.

-- 1. Catálogo inicial de productos
INSERT INTO products (sku, name, description, category, unit) VALUES
    ('P-001', 'Laptop Dell Latitude 5420', 'Laptop empresarial Intel Core i5 16GB RAM 512GB SSD', 'Computo', 'UNIDAD'),
    ('P-002', 'Monitor Samsung 27 4K', 'Monitor profesional IPS UHD 3840x2160', 'Monitores', 'UNIDAD'),
    ('P-003', 'Teclado Mecanico Logitech MX', 'Teclado inalambrico retroiluminado switch brown', 'Accesorios', 'UNIDAD'),
    ('P-004', 'Mouse Ergonomico Logitech MX Master 3', 'Mouse inalambrico recargable multidispositivo', 'Accesorios', 'UNIDAD'),
    ('P-005', 'Disco SSD Samsung 1TB NVMe', 'Unidad de estado solido PCIe 4.0 M.2', 'Almacenamiento', 'UNIDAD'),
    ('P-006', 'Memoria RAM Corsair 16GB DDR4', 'Modulo de memoria 3200MHz CL16', 'Componentes', 'UNIDAD')
ON CONFLICT (sku) DO NOTHING;

-- 2. Inicialización de inventario para cada producto del catálogo
INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity)
SELECT id, COALESCE(NULLIF(current_setting('warehouse.id', true), ''), 'WH-001'), 100, 0
FROM products
WHERE sku IN ('P-001', 'P-002', 'P-003', 'P-004', 'P-005', 'P-006')
ON CONFLICT (product_id) DO NOTHING;

-- 3. Registro de movimientos iniciales de recepción (RECEIPT)
INSERT INTO inventory_movements (product_id, warehouse_id, type, quantity, reference, idempotency_key)
SELECT id, COALESCE(NULLIF(current_setting('warehouse.id', true), ''), 'WH-001'), 'RECEIPT', 100, 'INITIAL_SEED', 'SEED-' || sku
FROM products
WHERE sku IN ('P-001', 'P-002', 'P-003', 'P-004', 'P-005', 'P-006')
ON CONFLICT (idempotency_key) DO NOTHING;
