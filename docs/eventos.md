# Eventos y mensajería (RabbitMQ)

## Topología

```text
Bodega WH-00X                                Central (EC2 hub)
-------------                                -----------------
API --(misma transacción)--> outbox_events
outbox_relay --publish--> [warehouse.events] (topic)
                               | inventory.#
                               v
                        central.projection --x-dead-letter--> [warehouse.dlx] --> central.projection.dlq
                               |
                         central_worker (proyección CQRS)

API central --publish--> [central.commands] (direct)
                               | transfer                         | report
                               v                                  v
                        central.transfers                  central.reports
                        (Saga)  --DLX--> .dlq              (batch S3) --DLX--> .dlq
```

| Exchange | Tipo | Routing key | Cola | Consumidor |
|---|---|---|---|---|
| `warehouse.events` | topic | `inventory.updated.<WH>` (binding `inventory.#`) | `central.projection` | `central_worker` → read model |
| `central.commands` | direct | `transfer` | `central.transfers` | `central_worker` → Saga |
| `central.commands` | direct | `report` | `central.reports` | `central_worker` → batch a S3 |
| `warehouse.dlx` | direct | nombre de la cola | `<cola>.dlq` | revisión manual / `POST /admin/dlq/<cola>/replay` |

Todas las colas y exchanges son durables y los mensajes se publican con `delivery_mode=2`. El volumen de RabbitMQ conserva los mensajes si el broker se reinicia. La topología se declara en `app/src/shared/messaging.py`.

## Contrato `INVENTORY_UPDATED` v1

Lo genera la API de bodega en la **misma transacción** que el movimiento (Transactional Outbox):

```json
{
  "event_id": "9e39f681-63ed-44e4-891a-27f8ffddad16",
  "event_type": "INVENTORY_UPDATED",
  "event_version": 1,
  "occurred_at": "2026-11-16T03:03:57.703951+00:00",
  "correlation_id": "COR-20261116-3b4afc86",
  "source": "warehouse-WH-002",
  "payload": {
    "warehouse_id": "WH-002",
    "product_id": 1,
    "sku": "P-001",
    "product_name": "Laptop",
    "movement_id": 7,
    "movement_type": "RECEIPT",
    "movement_quantity": 20,
    "reference": null,
    "quantity": 20,
    "reserved_quantity": 0
  }
}
```

Decisiones del contrato:
- **El balance completo** (`quantity`, `reserved_quantity`), y no solo el delta, hace que la proyección sea idempotente: aplicar dos veces el mismo estado da el mismo resultado.
- **`movement_id`** funciona como versión monótona por bodega. La proyección solo aplica un evento si su versión es mayor que la guardada, así que tolera eventos fuera de orden.
- **`sku`** es la identidad global del producto: los `product_id` son locales a cada bodega.
- **`event_version`**: cambios compatibles (campos nuevos y opcionales) mantienen la versión. Un cambio incompatible publica `event_version: 2` y el consumidor debe aceptar ambas versiones durante la transición.

## Comandos

```json
{"transfer_id": "TR-546A39C6"}      // central.transfers
{"job_id": "JOB-96888038"}          // central.reports
```

Los comandos solo llevan el identificador; el estado vive en la base de la central (`transfers`, `report_jobs`). Por eso un comando repetido es inofensivo: si la Saga o el job ya terminaron, se ignora.

## Garantías de entrega

| Tramo | Garantía | Cómo |
|---|---|---|
| API → outbox | exactamente una vez | misma transacción PostgreSQL que el movimiento |
| outbox → RabbitMQ | al menos una vez | publisher confirms + `mandatory`; solo se marca `SENT` si el broker enrutó el mensaje |
| RabbitMQ → worker | al menos una vez | `ack` manual después de procesar; si el worker cae, el mensaje vuelve a la cola |
| worker → read model | efecto exactamente una vez | tabla `processed_events (event_id, consumer)` en la misma transacción que la proyección |
| Saga → bodega | efecto exactamente una vez | cabecera `Idempotency-Key: TR-x:<paso>` con índice único en `inventory_movements` |

## Reintentos y DLQ

Política en `app/src/central/consumers.py`:

| Error | Ejemplo | ¿Retry? | ¿DLQ? | ¿Compensación? |
|---|---|---|---|---|
| Transitorio | base de la central caída, timeout, bodega 5xx | Sí, 3 veces con backoff de 1, 2 y 4 s (cabecera `x-retries`) | Al agotar los reintentos | Saga: sí, si ya había reservado (ver `on_transfer_dead`) |
| JSON inválido | `{esto no es json` | No | Inmediata | No |
| Campos faltantes | evento sin `sku` | No | Inmediata | No |
| Producto inexistente / sin stock | la bodega responde 404/400 | No | No: la Saga termina en `FAILED` | No hay nada que deshacer |
| Destino rechaza o no responde | bodega destino caída | Sí (transitorio) | Al agotar los reintentos | Sí: `COMPENSATING` → `RELEASE` → `CANCELLED` |
| Duplicado | mismo `event_id` o `transfer_id` | No | No: se confirma y se ignora | No |

Los mensajes en DLQ se inspeccionan en RabbitMQ Management (`http://<central>:15672`) o con `GET /admin/queues`. Se reinyectan con `POST /admin/dlq/<cola>/replay` una vez corregida la causa, por ejemplo cuando la base volvió.

## Trazabilidad

El `correlation_id` llega en `X-Correlation-ID`; si falta, se genera `COR-AAAAMMDD-xxxxxxxx`. Viaja en:

```text
HTTP (cabecera) -> API -> evento (campo correlation_id + propiedad AMQP) -> worker -> llamadas HTTP de la Saga (cabecera) -> eventos de la bodega -> proyección
```

Cada línea de log JSON incluye el `correlation_id`. Ejemplo real en el lab de una transferencia con `COR-TRAZA-001`, tomado de cuatro contenedores distintos:

```text
03:23:24.500 central-worker  transfer_status        RESERVING_SOURCE
03:23:24.502 central-api     http_request           POST /transfers 202
03:23:28.508 warehouse-api   http_request           GET /api/products/by-sku/P-001 200
03:23:28.523 warehouse-api   http_request           POST /api/inventory/movements 201
03:23:28.529 central-worker  transfer_status        SOURCE_RESERVED
03:23:29.396 outbox-relay    outbox_event_published f6baf4bb-...
03:23:29.401 central-worker  inventory_projected    WH-001 RESERVATION
```
