# Proyecto Integrador — Warehouse Cloud Platform

## Curso

**Computación en la Nube e Internet de las Cosas**

## Descripción

Este proyecto consiste en diseñar, implementar, desplegar y evaluar una plataforma distribuida para la gestión de múltiples bodegas o almacenes.

Cada bodega administra de manera autónoma:

- productos;
- inventario;
- movimientos de entrada y salida;
- reservas;
- usuarios/operadores;
- consultas frecuentes;
- procesos internos.

La plataforma evolucionará progresivamente desde una aplicación sencilla hasta una arquitectura distribuida capaz de manejar:

- múltiples APIs;
- múltiples bases de datos;
- Redis;
- RabbitMQ;
- workers asíncronos;
- balanceo de carga;
- escalamiento horizontal;
- transferencias entre bodegas;
- consistencia eventual;
- Saga y transacciones distribuidas;
- idempotencia;
- reintentos y DLQ;
- una plataforma central de consolidación;
- CQRS y modelos de lectura;
- S3;
- procesamiento Batch;
- AWS Lambda;
- observabilidad;
- pruebas de carga;
- y, como extensión, IoT dentro de las bodegas.

---

# 1. Problema

Una empresa administra varias bodegas distribuidas geográficamente.

Cada bodega recibe productos, almacena inventario, despacha pedidos y realiza ajustes. Algunas bodegas tienen mucho más tráfico que otras.

Por ejemplo:

| Bodega | Carga aproximada | Característica |
|---|---:|---|
| WH-001 | 50 req/s | Baja actividad |
| WH-002 | 800 req/s | Alta lectura |
| WH-003 | 20 req/s | Baja actividad |
| WH-004 | 2.000 req/s | Alta actividad |

La empresa necesita que:

1. cada bodega pueda operar de manera autónoma;
2. las consultas frecuentes sean rápidas;
3. las escrituras sean consistentes dentro de cada bodega;
4. los procesos pesados no bloqueen las APIs;
5. las bodegas puedan escalar de manera independiente;
6. se puedan transferir productos entre bodegas;
7. exista una visión consolidada de toda la empresa;
8. los procesos fallen de forma controlada;
9. exista trazabilidad de extremo a extremo;
10. la plataforma pueda crecer hacia AWS y eventualmente IoT.

---

# 2. Objetivo general

Construir una plataforma cloud distribuida que permita gestionar múltiples bodegas independientes y que evolucione progresivamente desde una aplicación CRUD hasta una arquitectura distribuida, asíncrona, observable y escalable.

El objetivo no es únicamente implementar tecnologías.

El objetivo es comprender **qué problema resuelve cada componente, cuándo introducirlo, qué trade-off genera y qué sucede cuando falla**.

---

# 3. Principio arquitectónico

La plataforma seguirá esta idea:

```text
                 CENTRAL PLATFORM
                       |
             +---------+---------+
             |                   |
        Global API          Global Workers
             |                   |
             |                RabbitMQ
             |                   |
     +-------+-------+-----------+---------+
     |               |                     |
     v               v                     v
 Warehouse A     Warehouse B           Warehouse C
     |               |                     |
 +---+---+        +---+---+            +---+---+
 |       |        |       |            |       |
API    Redis     API    Redis          API    Redis
 |       |        |       |            |       |
 v       |        v       |            v       |
DB A     |       DB B     |           DB C     |
```

Cada bodega es un **dominio operativo autónomo**.

La plataforma central es responsable principalmente de:

- consolidación;
- consultas globales;
- reportes;
- procesamiento empresarial;
- integración;
- analítica;
- coordinación de procesos distribuidos.

La central no debe convertirse desde el inicio en la única base de datos operacional de todas las bodegas. Eso eliminaría buena parte de los problemas distribuidos que el proyecto pretende estudiar.

---

# 4. Arquitectura evolutiva

El proyecto se desarrolla en fases.

```text
Fase 1
Bodega + API + PostgreSQL
        |
        v
Fase 2
Redis + Cache Aside
        |
        v
Fase 3
RabbitMQ + Workers
        |
        v
Fase 4
Múltiples bodegas
        |
        v
Fase 5
Load Balancer + Escalamiento
        |
        v
Fase 6
Transferencias + Saga
        |
        v
Fase 7
Central + CQRS + Read Model
        |
        v
Fase 8
S3 + Batch
        |
        v
Fase 9
Lambda
        |
        v
Fase 10
Fallos + Idempotencia + DLQ
        |
        v
Fase 11
Observabilidad + Load Testing
        |
        v
Fase 12
IoT en bodegas
```

Cada fase debe funcionar antes de pasar a la siguiente.

---

# 5. Tecnologías sugeridas

## Backend

- Python
- FastAPI o Flask

## Persistencia

- PostgreSQL

## Caché

- Redis

## Mensajería

- RabbitMQ

## Contenedores

- Docker
- Docker Compose

## Cloud

- AWS EC2
- Amazon ECR
- Amazon S3
- Amazon RDS
- AWS Lambda

## Infraestructura como código

- Terraform

## Testing

- pytest
- herramientas de carga como Locust, k6 o equivalente

## Observabilidad

- logs estructurados
- métricas
- correlation IDs
- health checks

## IoT — extensión

- MQTT
- simuladores de sensores

---

# 6. Modelo de dominio

## Product

```text
Product
-------
id
sku
name
description
category
unit
created_at
updated_at
```

## Inventory

```text
Inventory
---------
id
product_id
warehouse_id
quantity
reserved_quantity
updated_at
```

## Inventory Movement

```text
InventoryMovement
-----------------
id
product_id
warehouse_id
type
quantity
reference
created_at
```

Tipos posibles:

```text
RECEIPT
SHIPMENT
ADJUSTMENT
RESERVATION
RELEASE
TRANSFER_OUT
TRANSFER_IN
RETURN
```

## Transfer

```text
Transfer
--------
id
source_warehouse
destination_warehouse
product_id
quantity
status
created_at
updated_at
```

Estados:

```text
REQUESTED
RESERVING_SOURCE
SOURCE_RESERVED
IN_TRANSIT
DESTINATION_PENDING
DESTINATION_RECEIVED
COMPLETED
FAILED
COMPENSATING
CANCELLED
```

---

# 7. API inicial

La primera versión debe ser deliberadamente sencilla.

## Products

```http
POST /products
GET /products
GET /products/{id}
PUT /products/{id}
DELETE /products/{id}
```

## Inventory

```http
GET /inventory/{product_id}
POST /inventory/movements
GET /inventory/{product_id}/movements
```

## Health

```http
GET /health
```

Respuesta:

```json
{
  "status": "ok"
}
```

---

# 8. Fase 1 — Una bodega

## Objetivo

Comprender una arquitectura backend tradicional antes de introducir distribución.

```text
Client
   |
   v
 API
   |
   v
PostgreSQL
```

La aplicación debe permitir:

- crear productos;
- consultar productos;
- registrar entradas;
- registrar salidas;
- consultar inventario;
- consultar movimientos.

---

## 8.1 Reglas

Una salida no puede dejar el inventario negativo.

Ejemplo:

```text
Inventario = 10

Salida = 4

Inventario final = 6
```

Pero:

```text
Inventario = 10

Salida = 15
```

debe ser rechazada.

---

## 8.2 Transacción

Una operación de inventario debe modificar de forma atómica:

1. inventario;
2. movimiento.

Conceptualmente:

```text
BEGIN

UPDATE inventory
SET quantity = quantity - 4

INSERT INTO inventory_movements (...)

COMMIT
```

Si algo falla:

```text
ROLLBACK
```

---

# 9. Fase 2 — Redis

## Problema

Las consultas de inventario pueden ser mucho más frecuentes que las modificaciones.

Ejemplo:

```text
GET /inventory/P-001
GET /inventory/P-001
GET /inventory/P-001
GET /inventory/P-001
...
```

Consultar PostgreSQL constantemente puede generar una carga innecesaria.

---

# 9.1 Cache Aside

La API utilizará el patrón Cache Aside.

```text
Client
   |
   v
 API
   |
   v
 Redis
  /  \
HIT  MISS
      |
      v
 PostgreSQL
      |
      v
    Redis
```

Pseudoflujo:

```python
value = redis.get(key)

if value:
    return value

value = database.get_inventory(product_id)

redis.set(key, value, ex=30)

return value
```

---

# 9.2 Cache key

Ejemplo:

```text
warehouse:WH-001:inventory:P-001
```

La clave debe incluir el contexto de la bodega.

Esto evita colisiones entre:

```text
WH-001 / P-001
WH-002 / P-001
```

---

# 9.3 Cache invalidation

Supongamos:

```text
Redis = 100
PostgreSQL = 100
```

Se registra una salida:

```text
-10
```

La base queda:

```text
PostgreSQL = 90
```

pero Redis podría continuar:

```text
Redis = 100
```

Esto genera un dato obsoleto.

El estudiante deberá implementar al menos una estrategia:

### Estrategia A — Invalidación síncrona

```text
UPDATE DB
   |
   v
DELETE Redis key
```

### Estrategia B — Invalidación asíncrona

```text
API
 |
 +--> PostgreSQL
 |
 +--> RabbitMQ
        |
        v
   Cache Worker
        |
        v
      Redis
```

Se deberán comparar ambas alternativas.

---

# 10. Fase 3 — RabbitMQ y workers

## Problema

No todo debe ejecutarse dentro de la solicitud HTTP.

Ejemplos:

- generar reportes;
- actualizar modelos de lectura;
- invalidar cachés;
- auditoría;
- enviar notificaciones;
- procesar archivos;
- calcular estadísticas.

---

# 10.1 Evento

Después de una modificación:

```json
{
  "event_id": "evt-001",
  "event_type": "INVENTORY_UPDATED",
  "warehouse_id": "WH-001",
  "product_id": "P-001",
  "quantity": 90,
  "correlation_id": "cor-123",
  "timestamp": "2026-09-28T15:00:00Z"
}
```

---

# 10.2 RabbitMQ

```text
                    RabbitMQ
                       |
          +------------+------------+
          |            |            |
          v            v            v
    Cache Worker   Audit Worker   Analytics Worker
```

Una misma operación puede producir múltiples efectos secundarios sin hacer que la API ejecute todo sincrónicamente.

---

# 10.3 API asíncrona

Ejemplo:

```http
POST /reports
```

Respuesta:

```http
202 Accepted
```

```json
{
  "job_id": "JOB-001",
  "status": "PROCESSING"
}
```

El cliente puede consultar:

```http
GET /reports/jobs/JOB-001
```

---

# 11. Fase 4 — Múltiples bodegas

Ahora la arquitectura cambia.

```text
             CENTRAL
                |
       +--------+--------+
       |        |        |
       v        v        v
      WH1      WH2      WH3
       |        |        |
     API      API      API
       |        |        |
      DB       DB       DB
       |        |        |
    Redis    Redis    Redis
```

Cada bodega tendrá:

- API;
- PostgreSQL;
- Redis.

---

# 11.1 ¿Por qué bases separadas?

Para enseñar:

- autonomía;
- aislamiento;
- escalamiento independiente;
- fallos parciales;
- particionamiento;
- límites de dominio;
- consistencia distribuida.

Una caída de:

```text
WH-002
```

no debería detener necesariamente:

```text
WH-001
WH-003
```

---

# 11.2 ¿Por qué Redis por bodega?

Porque cada bodega tiene su propio workload.

Por ejemplo:

```text
WH-001 → 50 req/s
WH-002 → 800 req/s
WH-003 → 20 req/s
```

La bodega 002 puede necesitar más recursos de caché.

Esto introduce el concepto:

> Una bodega puede ser una unidad independiente de escalamiento.

---

# 12. Fase 5 — Load Balancing

Una bodega puede tener varias instancias de API.

```text
             Load Balancer
                  |
       +----------+----------+
       |          |          |
       v          v          v
     API-1      API-2      API-3
       |          |          |
       +----------+----------+
                  |
                Redis
                  |
              PostgreSQL
```

---

# 12.1 Problema de estado

Las instancias API deben ser stateless.

No se debe guardar información crítica de sesión únicamente en:

```text
API-1 memory
```

porque el siguiente request puede llegar a:

```text
API-2
```

El estado compartido debe estar en componentes externos apropiados:

- PostgreSQL;
- Redis;
- servicios externos.

---

# 12.2 Health checks

El load balancer debe verificar:

```http
GET /health
```

Una instancia que no responda correctamente debe dejar de recibir tráfico.

---

# 13. Fase 6 — Transferencias entre bodegas

Aquí aparece uno de los problemas más importantes del proyecto.

Supongamos:

```text
WH-001
Product P-001
Quantity = 100
```

y:

```text
WH-002
Product P-001
Quantity = 20
```

Se solicita:

```text
Transferir 30 unidades
```

Resultado esperado:

```text
WH-001 = 70
WH-002 = 50
```

Pero las bodegas tienen bases diferentes.

No existe una única transacción SQL:

```text
BEGIN
  DB A
  DB B
COMMIT
```

---

# 13.1 Problema distribuido

Puede ocurrir:

```text
1. WH-001 reserva 30
2. WH-002 falla
```

o:

```text
1. WH-001 descuenta 30
2. RabbitMQ falla
3. evento no se procesa
```

o:

```text
1. WH-001 procesa transferencia
2. mensaje se entrega nuevamente
3. WH-001 procesa dos veces
```

Esto introduce:

- consistencia eventual;
- idempotencia;
- reintentos;
- compensaciones;
- Saga.

---

# 13.2 Saga

Flujo:

```text
TRANSFER_REQUESTED
        |
        v
RESERVING_SOURCE
        |
        v
SOURCE_RESERVED
        |
        v
IN_TRANSIT
        |
        v
DESTINATION_RECEIVED
        |
        v
COMPLETED
```

Si falla:

```text
SOURCE_RESERVED
        |
        X
        |
        v
COMPENSATING
        |
        v
RESERVATION_RELEASED
```

---

# 13.3 API

```http
POST /transfers
```

Respuesta:

```http
202 Accepted
```

```json
{
  "transfer_id": "TR-001",
  "status": "PROCESSING"
}
```

La operación no necesita bloquear el request hasta que toda la transferencia termine.

---

# 13.4 Idempotencia

Cada operación distribuida debe tener un identificador único.

Ejemplo:

```text
transfer_id = TR-001
event_id = EVT-001
correlation_id = COR-001
```

Si el mismo mensaje llega dos veces:

```text
EVT-001
EVT-001
```

el worker debe detectar que ya fue procesado.

Tabla conceptual:

```text
processed_events
----------------
event_id
processed_at
consumer
```

---

# 14. Fase 7 — Plataforma central

Ahora aparece la necesidad de responder:

```http
GET /global/inventory/P-001
```

Supongamos:

```text
WH-001 = 100
WH-002 = 50
WH-003 = 80
WH-004 = 20
```

Total:

```text
250
```

---

# 14.1 Enfoque 1 — Consultar todas las bodegas

```text
                 Central API
                /    |    \
               /     |     \
             WH1    WH2    WH3
```

Problemas:

- latencia acumulada;
- dependencia de todas las bodegas;
- fallos parciales;
- muchas conexiones;
- difícil escalamiento.

---

# 14.2 Enfoque 2 — Read Model central

Las bodegas producen eventos:

```text
Warehouse APIs
      |
      v
   RabbitMQ
      |
      v
Inventory Projection Worker
      |
      v
Central Read Model
```

Entonces:

```text
GET /global/inventory/P-001
             |
             v
       Central Read DB
```

Esto introduce:

- CQRS;
- materialized views;
- proyecciones;
- consistencia eventual.

---

# 14.3 CQRS

La arquitectura puede separar:

```text
COMMAND SIDE
------------

Warehouse API
     |
     v
Operational DB


QUERY SIDE
----------

Events
   |
   v
Projection Worker
   |
   v
Read Model
```

La base operacional está optimizada para operaciones transaccionales.

El modelo de lectura está optimizado para consultas globales.

---

# 15. Fase 8 — S3

Los datos históricos o archivos grandes no deben necesariamente permanecer en la base operacional.

Ejemplos:

```text
s3://warehouse-platform/
    warehouses/
        WH-001/
            2026/
                09/
                    inventory-2026-09-28.json
```

También:

```text
s3://warehouse-platform/reports/
s3://warehouse-platform/audit/
s3://warehouse-platform/exports/
```

---

# 15.1 Casos de uso

S3 puede almacenar:

- reportes;
- archivos CSV;
- JSON;
- documentos;
- snapshots;
- históricos;
- resultados de procesos Batch.

---

# 16. Fase 9 — Batch Processing

Algunas tareas no necesitan respuesta inmediata.

Ejemplos:

- reporte diario;
- consolidación mensual;
- estadísticas;
- cálculo de indicadores;
- exportación histórica.

Flujo:

```text
                    +----------------+
                    |                |
Warehouses -------->| Batch Process  |
                    |                |
                    +-------+--------+
                            |
                            v
                           S3
```

Ejemplo:

```text
23:00
  |
  v
Procesar movimientos del día
  |
  v
Generar reporte
  |
  v
Guardar en S3
```

---

# 17. Fase 10 — AWS Lambda

Lambda debe introducirse después de comprender procesamiento Batch y eventos.

Ejemplo:

```text
S3
 |
 | ObjectCreated
 v
Lambda
 |
 +--> validar archivo
 +--> transformar datos
 +--> registrar metadata
 +--> publicar evento
```

Otro ejemplo:

```text
RabbitMQ / integración
       |
       v
    Evento
       |
       v
    Lambda
       |
       v
   procesamiento
```

El objetivo es comparar:

- worker persistente;
- proceso Batch;
- función serverless.

---

# 18. Fase 11 — Fallos distribuidos

Esta fase es obligatoria.

Los estudiantes deben provocar fallos intencionalmente.

## Caso 1 — Redis caído

```text
API → Redis X
```

La API debe continuar usando PostgreSQL.

---

## Caso 2 — RabbitMQ temporalmente caído

Las operaciones críticas deben definir qué hacer:

- rechazar;
- almacenar localmente;
- reintentar;
- publicar posteriormente.

El estudiante debe justificar su decisión.

---

## Caso 3 — Worker detenido

Los mensajes deben permanecer disponibles en la cola.

Al volver el worker:

```text
RabbitMQ
   |
   v
Worker
```

continúa el procesamiento.

---

## Caso 4 — Mensaje duplicado

```text
EVT-001
EVT-001
```

No debe duplicar una operación de inventario.

---

## Caso 5 — Bodega inaccesible

```text
WH-002 X
```

La central debe continuar funcionando, pero indicar que la información de esa bodega puede estar temporalmente desactualizada.

---

# 19. Reintentos y Dead Letter Queue

No todo error debe reintentarse indefinidamente.

Ejemplo:

```text
Message
   |
   v
Worker
   |
   X
   |
 Retry 1
   |
   X
   |
 Retry 2
   |
   X
   |
 Retry 3
   |
   v
 DLQ
```

La DLQ permite analizar mensajes que no pudieron procesarse.

---

# 19.1 Errores transitorios

Ejemplos:

- timeout;
- conexión temporalmente cerrada;
- servicio no disponible;
- rate limit.

Pueden ser reintentables.

---

# 19.2 Errores permanentes

Ejemplos:

- schema inválido;
- product_id inexistente;
- evento corrupto;
- dato obligatorio ausente.

No necesariamente deben reintentarse.

---

# 20. Observabilidad

Cada request y cada evento debe poder seguirse.

Se utilizará:

```text
correlation_id
```

Ejemplo:

```text
COR-20260928-001
```

Flujo:

```text
Client
 |
 v
API
 | correlation_id
 v
RabbitMQ
 | correlation_id
 v
Worker
 | correlation_id
 v
Database
```

Logs:

```json
{
  "timestamp": "...",
  "service": "inventory-api",
  "level": "INFO",
  "event": "inventory_updated",
  "warehouse_id": "WH-001",
  "product_id": "P-001",
  "correlation_id": "COR-001"
}
```

---

# 21. Métricas

Como mínimo:

## API

- request count;
- error rate;
- latency;
- throughput.

## Redis

- hit rate;
- miss rate;
- memory usage.

## RabbitMQ

- queue depth;
- processing rate;
- retry count;
- DLQ count.

## PostgreSQL

- conexiones;
- query latency;
- locks;
- errores.

## Workers

- jobs procesados;
- jobs fallidos;
- tiempo de procesamiento.

---

# 22. Pruebas de carga

El sistema debe probarse con diferentes escenarios.

Ejemplo:

```text
100 usuarios
500 usuarios
1.000 usuarios
5.000 usuarios
```

Medir:

```text
Requests/sec
P50
P95
P99
Error rate
CPU
Memory
DB connections
Redis hit rate
Queue depth
```

---

# 22.1 Comparación sin Redis vs con Redis

Ejecutar:

```text
GET /inventory/P-001
```

con Redis deshabilitado.

Luego:

```text
GET /inventory/P-001
```

con Redis.

Comparar:

- latencia;
- throughput;
- carga de PostgreSQL;
- comportamiento bajo concurrencia.

---

# 22.2 Prueba de escalamiento

Comparar:

```text
1 API instance
```

contra:

```text
3 API instances
```

y analizar:

- throughput;
- latencia;
- distribución de requests;
- utilización de CPU.

---

# 23. Fase 12 — IoT como extensión

Una vez terminada la plataforma distribuida, cada bodega puede incorporar sensores.

Ejemplos:

- temperatura;
- humedad;
- apertura de puertas;
- movimiento;
- consumo energético;
- ocupación.

Arquitectura:

```text
Sensor
   |
   v
MQTT
   |
   v
Edge / Gateway
   |
   v
Central Platform
```

La bodega podría tener:

```text
Warehouse
 |
 +-- Inventory API
 +-- PostgreSQL
 +-- Redis
 +-- RabbitMQ
 |
 +-- IoT
      |
      +-- temperature
      +-- humidity
      +-- movement
```

---

# 23.1 Ejemplo

Sensor:

```json
{
  "sensor_id": "TEMP-001",
  "warehouse_id": "WH-001",
  "temperature": 8.4,
  "timestamp": "2026-09-28T15:00:00Z"
}
```

MQTT topic:

```text
warehouses/WH-001/sensors/TEMP-001
```

La plataforma puede generar:

```text
Sensor
  |
  v
MQTT
  |
  v
Ingestion Service
  |
  v
RabbitMQ
  |
  +--> Storage Worker
  +--> Alert Worker
  +--> Analytics Worker
```

---

# 24. Problemas distribuidos adicionales con IoT

La extensión IoT debe introducir:

- mensajes duplicados;
- mensajes fuera de orden;
- pérdida temporal de conectividad;
- buffering local;
- timestamps;
- sequence numbers;
- idempotencia;
- procesamiento eventual.

Ejemplo:

```json
{
  "event_id": "EVT-100",
  "sequence_number": 150,
  "warehouse_id": "WH-001",
  "sensor_id": "TEMP-001",
  "value": 8.4
}
```

---

# 25. Docker Compose

Durante desarrollo, cada equipo debe poder levantar su entorno.

Ejemplo conceptual:

```yaml
services:

  warehouse-api:
    build: ./api
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres

  redis:
    image: redis

  rabbitmq:
    image: rabbitmq
```

En fases posteriores puede existir:

```text
warehouse-001
warehouse-002
warehouse-003
central-api
rabbitmq
```

---

# 26. Estructura sugerida del repositorio

```text
warehouse-cloud-platform/
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── distributed-transactions.md
│   ├── caching.md
│   └── observability.md
│
├── services/
│   ├── warehouse-api/
│   ├── central-api/
│   ├── inventory-worker/
│   ├── transfer-worker/
│   ├── cache-worker/
│   └── projection-worker/
│
├── infrastructure/
│   ├── docker/
│   ├── compose/
│   └── terraform/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
│
├── scripts/
│
└── README.md
```

---

# 27. Contratos de eventos

Los eventos deben tener una estructura consistente.

Ejemplo:

```json
{
  "event_id": "EVT-001",
  "event_type": "INVENTORY_UPDATED",
  "event_version": 1,
  "occurred_at": "2026-09-28T15:00:00Z",
  "correlation_id": "COR-001",
  "source": "warehouse-001",
  "payload": {
    "warehouse_id": "WH-001",
    "product_id": "P-001",
    "quantity": 90
  }
}
```

Esto permite enseñar:

- event contracts;
- versionamiento;
- backward compatibility;
- tracing;
- idempotencia.

---

# 28. Seguridad

El proyecto debe considerar:

- variables de entorno;
- secretos fuera del código;
- autenticación;
- autorización;
- HTTPS en ambientes reales;
- mínimo privilegio;
- separación entre credenciales de desarrollo y producción;
- validación de entrada;
- protección contra SQL injection;
- control de acceso a S3.

Nunca almacenar:

```text
password
secret
API key
AWS credential
```

directamente en el repositorio.

---

# 29. Despliegue en AWS

La arquitectura final puede evolucionar hacia:

```text
                 Internet
                    |
              Load Balancer
                    |
              Central API
                    |
          +---------+---------+
          |                   |
       RabbitMQ             Redis
          |
          +--------------------+
          |
    +-----+-----+-----+
    |     |     |     |
   WH1   WH2   WH3   WH4
    |     |     |     |
   API   API   API   API
    |     |     |     |
  RDS/  RDS/  RDS/  RDS/
```

Servicios AWS a estudiar:

- EC2;
- ECR;
- RDS;
- S3;
- Lambda;
- IAM;
- CloudWatch;
- VPC;
- Security Groups;
- Load Balancer.

---

# 30. Terraform

La infraestructura debe declararse como código.

Ejemplo conceptual:

```text
terraform/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
└── modules/
    ├── network/
    ├── database/
    ├── compute/
    ├── storage/
    └── load_balancer/
```

Objetivos:

- reproducibilidad;
- versionamiento;
- automatización;
- infraestructura declarativa;
- eliminación controlada;
- ambientes consistentes.

---

# 31. Entregables

Cada equipo debe entregar:

## Entregable 1 — Arquitectura

Diagrama con:

- APIs;
- bases de datos;
- Redis;
- RabbitMQ;
- workers;
- central;
- load balancer;
- S3;
- Lambda;
- IoT si aplica.

---

## Entregable 2 — Backend

Código de:

- Warehouse API;
- Central API;
- workers;
- procesamiento de eventos.

---

## Entregable 3 — Infraestructura

Dockerfiles y Docker Compose.

---

## Entregable 4 — Persistencia

Scripts:

```text
schema.sql
seed.sql
migrations/
```

---

## Entregable 5 — Eventos

Documentación de:

- exchanges;
- queues;
- routing keys;
- eventos;
- consumidores;
- reintentos;
- DLQ.

---

## Entregable 6 — AWS

Infraestructura desplegada o documentada mediante:

- EC2;
- ECR;
- RDS;
- S3;
- Lambda.

---

## Entregable 7 — Terraform

Código de infraestructura.

---

## Entregable 8 — Pruebas

Debe existir evidencia de:

- pruebas unitarias;
- pruebas de integración;
- pruebas de carga;
- pruebas de fallos;
- duplicación de mensajes;
- caída de Redis;
- caída de workers;
- recuperación.

---

# 32. Evaluación técnica sugerida

La evaluación puede considerar:

| Área | Qué se evalúa |
|---|---|
| Dominio | Modelo correcto de bodegas e inventario |
| API | Diseño y validación |
| PostgreSQL | Transacciones y consistencia |
| Redis | Cache Aside e invalidación |
| RabbitMQ | Eventos y consumidores |
| Workers | Procesamiento asíncrono |
| Distribución | Independencia entre bodegas |
| Saga | Transferencias |
| Idempotencia | Manejo de duplicados |
| CQRS | Read Model |
| S3 | Persistencia de archivos |
| Batch | Procesamiento masivo |
| Lambda | Serverless |
| Docker | Contenedorización |
| AWS | Despliegue |
| Terraform | IaC |
| Observabilidad | Logs, métricas y correlation ID |
| Testing | Carga y fallos |
| Arquitectura | Justificación de decisiones |

---

# 33. Preguntas de defensa

Cada equipo debe estar preparado para responder:

### Arquitectura

1. ¿Por qué cada bodega tiene su propia base?
2. ¿Por qué no utilizar una única base central?
3. ¿Qué sucede si una bodega deja de responder?
4. ¿Cómo escalaría una sola bodega?
5. ¿Cómo evitaría que una bodega afecte a las demás?

### Redis

6. ¿Por qué utilizar Redis?
7. ¿Qué sucede si Redis está caído?
8. ¿Cómo se invalida la caché?
9. ¿Qué es un cache miss?
10. ¿Qué problema aparece con datos obsoletos?

### RabbitMQ

11. ¿Por qué usar un broker?
12. ¿Qué diferencia existe entre procesamiento síncrono y asíncrono?
13. ¿Qué sucede si un worker falla?
14. ¿Qué es una DLQ?
15. ¿Cómo evitar mensajes duplicados?

### Distribución

16. ¿Por qué una transferencia entre bodegas es una operación distribuida?
17. ¿Qué es Saga?
18. ¿Qué es una compensación?
19. ¿Qué significa consistencia eventual?
20. ¿Qué sucede si la bodega destino no responde?

### CQRS

21. ¿Por qué crear un Read Model?
22. ¿Por qué no consultar todas las bodegas?
23. ¿Qué significa que el Read Model pueda estar desactualizado?
24. ¿Qué ventaja ofrece una proyección?

### Cloud

25. ¿Por qué utilizar EC2?
26. ¿Qué problema resuelve ECR?
27. ¿Qué diferencia existe entre RDS y PostgreSQL local?
28. ¿Qué problema resuelve S3?
29. ¿Cuándo utilizar Lambda?

### Observabilidad

30. ¿Cómo seguir una operación de extremo a extremo?
31. ¿Qué información debe contener un log?
32. ¿Cómo detectar una cola saturada?
33. ¿Cómo identificar una consulta lenta?

---

# 34. Criterio central del proyecto

El proyecto no debe evaluarse únicamente por:

> "¿Funciona?"

También debe evaluarse:

> "¿Por qué está construido de esta manera?"

Cada decisión arquitectónica debe documentar:

```text
Problema
   ↓
Alternativas
   ↓
Decisión
   ↓
Trade-offs
   ↓
Consecuencias
```

Ejemplo:

```text
Problema:
Muchas consultas de inventario.

Alternativas:
1. Consultar PostgreSQL siempre.
2. Usar Redis.

Decisión:
Usar Redis con Cache Aside.

Beneficio:
Menor latencia y menor carga sobre PostgreSQL.

Trade-off:
La caché puede quedar desactualizada.

Mitigación:
TTL + invalidación por evento.
```

---

# 35. Resultado final esperado

Al terminar el proyecto, el estudiante debe ser capaz de explicar y demostrar una arquitectura como:

```text
                              INTERNET
                                  |
                           Load Balancer
                                  |
                            Central API
                                  |
                    +-------------+-------------+
                    |                           |
                Read Model                 RabbitMQ
                    |                           |
                    |              +------------+------------+
                    |              |            |            |
                    |           Workers      Workers      Workers
                    |
        +-----------+-----------+-----------+
        |                       |           |
        v                       v           v
   Warehouse A             Warehouse B  Warehouse C
        |                       |           |
   +----+----+             +----+----+ +----+----+
   |         |             |         | |         |
  API      Redis           API      Redis API   Redis
   |         |             |         | |         |
   v         |             v         | v         |
PostgreSQL  |          PostgreSQL   | PostgreSQL|
   |         |             |         | |         |
   +---------+-------------+---------+-+---------+
                         |
                     Events
                         |
                      RabbitMQ
                         |
             +-----------+-----------+
             |                       |
             v                       v
            S3                    Lambda
             |
             v
        Batch Reports
```

Y deberá ser capaz de explicar:

- cómo funciona;
- por qué funciona;
- qué sucede cuando falla;
- cómo escala;
- dónde existe consistencia fuerte;
- dónde existe consistencia eventual;
- cómo se recupera;
- cómo se observa;
- cómo se prueba;
- y cómo se llevaría progresivamente a producción.

---

# 36. Regla pedagógica final

No implementar toda la arquitectura desde el primer día.

El aprendizaje debe seguir:

```text
Simple
  ↓
Cache
  ↓
Asincronismo
  ↓
Distribución
  ↓
Escalamiento
  ↓
Transacciones distribuidas
  ↓
CQRS
  ↓
Cloud
  ↓
Serverless
  ↓
Observabilidad
  ↓
IoT
```

La complejidad debe aparecer porque existe un problema que la justifica.

Ese principio será parte fundamental de la evaluación del proyecto.
