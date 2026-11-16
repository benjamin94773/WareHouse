# Pruebas y evidencia

Las pruebas se ejecutaron el 2026-11-16 (UTC) sobre la infraestructura del Learner Lab:
- 4 EC2 t3.small: central + wh-001/002/003.
- 3 réplicas de API por bodega.

## 1. Pruebas unitarias y de integración

| Suite | Cobertura | Comando |
|---|---|---|
| Bodega (16) | reglas de inventario, rollback, ADJUSTMENT, reservas, validaciones (422/404/409), CRUD, Cache Aside hit/miss/invalidación, Redis caído, correlation ID, contrato del evento, Idempotency-Key, TRANSFER_OUT | `cd app/src/backend/app && pytest -q` |
| Central (18) | proyección idempotente y fuera de orden, errores permanentes → DLQ, reintentos, inventario global con bodega caída, Saga (6 escenarios), batch reejecutable, métricas sin broker | `cd app/src/central && pytest -q` |
| Lambda (3) | validación, resumen y formatos de evento | `cd lambda/report_validator && pytest -q` |

Las pruebas usan SQLite y dobles en memoria de Redis, RabbitMQ y las bodegas, así que corren sin Docker. La integración real se validó en el lab (secciones 2 y 3).

## 2. Pruebas de fallos en el lab (Fases 4, 5, 6 y 10)

Cada prueba se ejecutó por SSH sobre los contenedores reales. Los resultados son los observados.

| # | Experimento | Cómo se provocó | Resultado observado |
|---|---|---|---|
| F1 | Redis caído | `docker compose stop redis` en wh-001 | `GET /inventory/1` siguió en 200 con `X-Cache: MISS`; el movimiento respondió 201. Log `redis_unavailable` con `fallback: postgres`. |
| F2 | RabbitMQ caído | `stop rabbitmq` en la central | Dos salidas en WH-001 respondieron 201 y quedaron `PENDING` en el outbox. `POST /transfers` respondió **503** (rechazo deliberado, ADR-004). Al volver el broker, el outbox se vació en **16 s** y la central pasó de 143 a 123. |
| F3 | Worker detenido | `stop central_worker` | 5 movimientos quedaron en `central.projection` (profundidad 5); la API central siguió respondiendo. Al reiniciar el worker, la cola se vació en **2 s** y el total pasó de 173 a 178. |
| F4 | Mensaje duplicado | `POST /admin/inject/duplicate` y `POST /transfers/{id}/redeliver` sobre una transferencia completada | Logs `duplicate_event_ignored` y `duplicate_command_ignored`; el total global no cambió (178 → 178). |
| F5 | Bodega inaccesible | `docker compose stop` de toda wh-002 | WH-001 (201) y WH-003 (200) siguieron operando. El read model respondió total 180 con WH-002 marcada **`STALE`** y una advertencia; el scatter-gather devolvió un total **incompleto (161)**. Al volver, WH-002 recuperó el estado `ok`. |
| F6a | Mensajes inválidos | `inject/invalid_json` y `inject/missing_fields` | Los dos fueron directo a `central.projection.dlq`, sin reintentos. |
| F6b | Error transitorio | `stop central_db` y un movimiento | `message_retry` intentos 1, 2 y 3 (backoff de 1, 2 y 4 s) y luego DLQ a los ~9 s. Con la base de vuelta, `POST /admin/dlq/central.projection/replay` reprocesó el evento (178 → 180); los 2 inválidos volvieron a la DLQ. |
| LB | Réplica caída | `docker kill` de 1 de las 3 réplicas de WH-001, 3 rondas de 40 requests | **118/120 con 200**. Nginx reintenta en otra réplica los requests que caen en la muerta (`proxy_next_upstream`). En 2 rondas, 1 request recibió 502 en los primeros segundos, mientras Nginx sacaba la réplica del pool (re-resolución DNS cada 5 s). |

### Saga (Fase 6)

| Escenario | Transferencia | Historial | Efecto en inventario |
|---|---|---|---|
| Camino feliz (destino sin el sku) | WH-001 → WH-003, 30 u. | REQUESTED → RESERVING_SOURCE → SOURCE_RESERVED → IN_TRANSIT → DESTINATION_RECEIVED → COMPLETED | WH-001 100 → 70, WH-003 0 → 30 (producto creado en destino) |
| Fallo antes de reservar | `simulate_failure=before_reserve` | REQUESTED → FAILED | sin cambios |
| Fallo después de reservar | `simulate_failure=after_reserve` | … SOURCE_RESERVED → COMPENSATING → CANCELLED | reserva liberada; sin cambios netos |
| Sin stock | WH-003 → WH-002, 999 u. | REQUESTED → RESERVING_SOURCE → FAILED (`Stock insuficiente`) | sin cambios |
| Destino caído | WH-001 → WH-002 con wh-002 detenida | … IN_TRANSIT → COMPENSATING → CANCELLED en 10 s (3 reintentos) | WH-001 recuperó las 10 u.; `reserved_quantity` = 0 |
| Worker reiniciado a mitad | `step_delay=4`, `docker restart central_worker` en `SOURCE_RESERVED` | continuó hasta COMPLETED | WH-001 131 → 101, WH-002 20 → 50, sin duplicados |
| Comando duplicado | `redeliver` sobre la anterior | ignorado | sin cambios |

### Trazabilidad (Fase 11)

La transferencia con `X-Correlation-ID: COR-TRAZA-001` aparece con el mismo `correlation_id` en los logs de `central-api`, `central-worker`, `warehouse-api` (WH-001 y WH-002), `outbox-relay` y en la proyección. El extracto está en `docs/eventos.md#trazabilidad`. Comando para reproducirlo:

```bash
ssh -i labsuser.pem ubuntu@<ip> "cd app && docker compose -f docker-compose.<central|warehouse>.yml logs --no-log-prefix | grep COR-TRAZA-001"
```

### Fases 8 y 9

`POST /reports` respondió 202. El worker generó `reports/daily/2026/11/16/report-2026-11-16.json` y un snapshot por bodega en S3. EventBridge disparó la Lambda, que dejó `metadata/...meta.json` (`valid: true`) y publicó el resultado en `/integrations/lambda-events`. Todo el flujo tomó ~5 s.

## 3. Pruebas de carga (Fase 11)

Escenario: lecturas `GET /api/inventory/1` sobre el LB de WH-001 (t3.small, 2 vCPU).
- **Generador:** k6 en la EC2 central, dentro de AWS, para no medir la latencia de Internet.
- **Modo:** lazo cerrado sin pausa: cada usuario envía el siguiente request apenas recibe la respuesta.
- **Duración:** 25 s por escalón.
- **Datos crudos:** `tests/load/results/`, con CSV/JSON por corrida, `/metrics` antes y después, y `docker stats` a mitad de cada corrida.

### 3.1 Redis ON vs Redis OFF (3 réplicas)

| Usuarios | Redis | RPS | p50 | p95 | p99 | Errores | CPU (APIs / PostgreSQL) |
|---:|---|---:|---:|---:|---:|---:|---|
| 100 | ON | **541** | 132 ms | 514 ms | 593 ms | 0 % | ~170 % / 0,1 % |
| 100 | OFF | 219 | 160 ms | 2 650 ms | 4 628 ms | 0 % | ~150 % / 33 % |
| 500 | ON | 523 | 522 ms | 2 874 ms | 3 432 ms | 0 % | — |
| 500 | OFF | 32 | 15 002 ms | 15 065 ms | 15 119 ms | **92 %** | ~87 % / 10 % |
| 1000 | ON | 531 | 1 312 ms | 5 158 ms | 5 551 ms | 2,9 % | ~170 % / 0,1 % |
| 1000 | OFF | 68 | 15 055 ms | 15 520 ms | 15 564 ms | **97 %** | — |

- Con Redis, el throughput es 2,5 veces mayor (541 vs 219 RPS) y PostgreSQL queda prácticamente sin carga (0,1 % de CPU, 5 conexiones contra 31). El hit ratio fue del 99,9 %.
- Sin Redis, cada request abre una transacción, hace un `SELECT` y serializa el resultado. Desde 500 usuarios la cola supera el timeout del LB (15 s) y la bodega **colapsa por congestión**: procesa requests cuyos clientes ya se rindieron.
- **Cuello de botella:** CPU de las APIs Python. Con Redis, ~530 RPS es el techo de 2 vCPU: más usuarios solo agregan latencia.

### 3.2 1 réplica vs 3 réplicas (Redis ON)

| Usuarios | Réplicas | RPS | p50 | p95 | Errores | CPU APIs |
|---:|---:|---:|---:|---:|---:|---|
| 100 | 1 | 437 | 223 ms | 295 ms | 0 % | ~104 % (1 núcleo) |
| 100 | 3 | **541** | 132 ms | 514 ms | 0 % | ~170 % (2 núcleos) |
| 500 | 1 | 370 | 1 270 ms | 1 737 ms | 0 % | — |
| 500 | 3 | 523 | 522 ms | 2 874 ms | 0 % | — |
| 1000 | 1 | 67 | 15 179 ms | 15 259 ms | **99,8 %** | ~104 % |
| 1000 | 3 | 531 | 1 312 ms | 5 158 ms | 2,9 % | ~170 % |

- Un proceso Python usa un solo núcleo. **3 réplicas aprovechan los 2 vCPU** (+24 % de RPS con 100 usuarios) y, sobre todo, toleran más concurrencia: con 1000 usuarios, 1 réplica colapsa (99,8 % de errores) y 3 réplicas mantienen 531 RPS con 2,9 % de errores.
- Más allá de 2 núcleos, más réplicas en la misma máquina no suman: el siguiente paso es otra instancia, o una más grande, detrás de un LB (ADR-008).
- El balanceo es round-robin (cabecera `X-Upstream` con las 3 IPs alternando) y las réplicas son stateless: tras el primer MISS, las otras réplicas obtienen HIT porque Redis es compartido.

### 3.3 Carga distinta por bodega (Fase 4)

`warehouse_profiles.js`, 30 s a tasa constante, las 3 bodegas a la vez:

| Bodega | Tasa pedida | Requests atendidos | p50 | p95 | p99 | Errores |
|---|---:|---:|---:|---:|---:|---:|
| WH-001 | 50 req/s | 1 501 | 3,6 ms | 8,2 ms | 27,8 ms | 0 % |
| WH-002 | 800 req/s | 15 615 (~520 req/s) | 866 ms | 4 310 ms | 4 660 ms | 0 % (8 385 iteraciones descartadas por k6) |
| WH-003 | 20 req/s | 601 | 3,8 ms | 10 ms | 51,9 ms | 0 % |

WH-002 está saturada: no alcanza 800 req/s y su latencia sube a segundos. **WH-001 y WH-003 siguen en milisegundos** porque no comparten máquina, base, Redis ni LB. Esto confirma la autonomía de la Fase 4 y muestra por qué no conviene escalar todas las bodegas igual: solo WH-002 necesita más capacidad, aproximadamente el doble según el techo medido de ~530 req/s por t3.small.

### 3.4 Hallazgos de las pruebas de carga y correcciones

| # | Síntoma | Causa | Corrección (commit) |
|---|---|---|---|
| 1 | Redis OFF y 100 usuarios: 48 RPS, p95 15 s, 45 conexiones `idle in transaction`, CPU ociosa | Interbloqueo: 40 hilos de FastAPI y solo 15 conexiones en el pool; el cierre de `get_db` necesita un hilo libre | pool de 40 conexiones y `pool_timeout` de 5 s; PostgreSQL con `max_connections=200` (`fix(db)`). Resultado: 219 RPS sin errores |
| 2 | 500 usuarios: 99,97 % de errores a 5 700 RPS con APIs ociosas | Nginx contaba los timeouts por sobrecarga como fallas, desactivaba las 3 réplicas y respondía `no live upstreams` | `max_fails=0`, re-resolución DNS y `proxy_next_upstream_timeout 3s` (`fix(lb)`). Resultado: 1000 usuarios con 2,9 % de errores |
| 3 | Se probó load shedding (`--limit-concurrency 100`) | En lazo cerrado los 503 inmediatos se convierten en más requests: 72 % de rechazos con 100 usuarios en 1 réplica | descartado |

Los resultados con el pool roto quedan en `tests/load/results/antes-fix-pool/` como evidencia del problema.

### 3.5 Propuestas de mejora

1. **Escalar horizontalmente WH-002:** ALB + Auto Scaling Group con 2–3 instancias. Su techo de ~530 req/s por t3.small no cubre 800 req/s.
2. **Load shedding con un generador realista:** límite de concurrencia por réplica y clientes con *think time* o backoff ante 503, para cortar el colapso por congestión sin generar tormentas de reintentos.
3. **Más trabajo por núcleo:** endpoints `async` con un driver asíncrono, o más workers de uvicorn por réplica.
4. **5000 usuarios:** queda fuera del alcance del lab. Una t3.small llega a su techo con ~500 usuarios en lazo cerrado, y generar 5000 usuarios requiere varias máquinas de carga.


## 4. Cómo repetir las pruebas

```bash
C=http://<ip-central>:8080; W1=http://<ip-wh-001>/api
ssh -i labsuser.pem ubuntu@<ip-wh-001>     # luego: cd app

# F1 Redis caído
docker compose -f docker-compose.warehouse.yml stop redis
curl -i $W1/inventory/1                     # 200, X-Cache: MISS
docker compose -f docker-compose.warehouse.yml start redis

# F2 RabbitMQ caído (en la central)
docker compose -f docker-compose.central.yml stop rabbitmq
curl -X POST $W1/inventory/movements -H 'Content-Type: application/json' -d '{"product_id":1,"type":"SHIPMENT","quantity":5}'
curl $W1/inventory/outbox/audit             # PENDING
docker compose -f docker-compose.central.yml start rabbitmq

# F3 worker detenido
docker compose -f docker-compose.central.yml stop central_worker
curl $C/admin/queues                         # central.projection crece
docker compose -f docker-compose.central.yml start central_worker

# F4 / F6
curl -X POST $C/admin/inject/duplicate
curl -X POST $C/admin/inject/invalid_json
curl -X POST $C/admin/dlq/central.projection/replay

# F5 bodega caída (en wh-002)
docker compose -f docker-compose.warehouse.yml stop
curl $C/global/inventory/P-001               # WH-002 stale + warning
curl $C/global/inventory/P-001/live          # total incompleto

# Saga
curl -X POST $C/transfers -H 'Content-Type: application/json' \
  -d '{"source":"WH-001","destination":"WH-002","sku":"P-001","quantity":10,"simulate_failure":"after_reserve"}'
curl $C/transfers/<id>
```
