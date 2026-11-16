# Fase 1 — Una Bodega: API + PostgreSQL

## Objetivo

Construir la primera versión funcional del sistema sin distribución.

```text
Client
  |
  v
API
  |
  v
PostgreSQL
```

## Requisitos

La API debe permitir:

- crear productos;
- consultar productos;
- consultar inventario;
- registrar entradas;
- registrar salidas;
- consultar movimientos.

## Endpoints mínimos

```http
POST /products
GET /products
GET /products/{id}

GET /inventory/{product_id}

POST /inventory/movements

GET /inventory/{product_id}/movements

GET /health
```

## Regla de negocio

Nunca permitir:

```text
quantity < 0
```

## Transacción

Una salida debe modificar inventario y crear el movimiento dentro de una misma transacción.

```text
BEGIN
  UPDATE inventory
  INSERT inventory_movement
COMMIT
```

Si una operación falla:

```text
ROLLBACK
```

## Entregables

1. API.
2. PostgreSQL.
3. Dockerfile.
4. docker-compose.yml.
5. schema.sql.
6. README.
7. colección de pruebas HTTP.
8. pruebas unitarias.
9. pruebas de integración.

## Preguntas

- ¿Qué información es estado?
- ¿Qué información debe persistir?
- ¿Por qué una salida necesita una transacción?
- ¿Qué sucede con dos salidas concurrentes?
