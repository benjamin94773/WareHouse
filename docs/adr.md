# Decisiones de arquitectura (ADR)

Formato de la guía de entrega: Contexto → Alternativas → Decisión → Consecuencias.

---

## ADR-001 — Una base PostgreSQL por bodega

**Contexto.** Cada bodega opera de forma autónoma y con cargas muy distintas (WH-002 recibe 16 veces más tráfico que WH-001).

**Alternativas.** (1) Una base central compartida. (2) Una base por bodega.

**Decisión.** Una base por bodega, en su propia EC2 y su propia VPC. Las bodegas no comparten bases ni tienen red entre ellas (solo peering con la central).

**Consecuencias.**
- (+) La caída de WH-002 no afecta a WH-001 ni a WH-003 (comprobado en el lab, F5).
- (+) Cada bodega escala por separado.
- (−) No existe una transacción entre bodegas: las transferencias necesitan una Saga (ADR-006) y la vista global es eventualmente consistente (ADR-005).

---

## ADR-002 — Redis con Cache Aside e invalidación síncrona

**Contexto.** `GET /inventory/{id}` es mucho más frecuente que las escrituras.

**Alternativas.**
1. Leer siempre de PostgreSQL.
2. Cache Aside con invalidación síncrona: `DELETE` de la clave después del commit.
3. Cache Aside con invalidación asíncrona: un worker escucha eventos y borra la clave.

**Decisión.** Opción 2, más TTL de 30 s como red de seguridad. La clave es `warehouse:<WH>:inventory:<product_id>`.

| | Síncrona (elegida) | Asíncrona |
|---|---|---|
| Ventana de dato obsoleto | ~0 (se borra justo después del commit) | hasta que el worker procese el evento |
| Latencia de la escritura | +1 comando Redis (~1 ms; 200 ms de timeout máximo) | sin costo extra |
| Dependencias | la API habla con Redis | API → RabbitMQ → worker → Redis |
| Si Redis cae | la escritura sigue; el TTL corrige | igual, y además depende del broker |

**Consecuencias.**
- Redis nunca es la fuente de verdad. Si falla, la API lee de PostgreSQL y omite Redis durante 5 s para no sumar timeouts en cada request (comprobado en el lab, F1).
- `CACHE_ENABLED=false` permite medir Redis OFF.
- Redis es compartido por todas las réplicas de la bodega: con un Redis por réplica, cada una tendría su propia caché y la invalidación de una no limpiaría las demás.

---

## ADR-003 — RabbitMQ con Transactional Outbox en las bodegas

**Contexto.** Los efectos secundarios (read model, reportes) no deben bloquear la API. Si se publica directamente después del commit, un fallo entre ambos pasos pierde el evento.

**Alternativas.** (1) Publicar dentro del request. (2) Transactional Outbox + relay. (3) CDC (Debezium).

**Decisión.** Outbox: el evento se inserta en `outbox_events` en la misma transacción que el movimiento. Un proceso `outbox_relay` (contenedor propio, uno por bodega) lo publica con publisher confirms.

**Consecuencias.**
- (+) Con RabbitMQ caído la bodega sigue aceptando movimientos (201) y los eventos esperan en `PENDING`. Al volver el broker se publican solos: en el lab tardó 16 s (F2).
- (+) El relay va separado de las 3 réplicas de la API; si no, habría 3 publicadores compitiendo. Igual usa `FOR UPDATE SKIP LOCKED` por si se escala.
- (−) Entrega al menos una vez: los consumidores deben ser idempotentes (ADR-007).

---

## ADR-004 — Qué hacer con operaciones críticas si RabbitMQ está caído

**Contexto.** La Fase 10 pide decidir entre rechazar, guardar localmente, reintentar o publicar después.

**Decisión.**

| Operación | Estrategia | Justificación |
|---|---|---|
| Movimiento en bodega | **Guardar localmente y publicar después** (outbox) | El movimiento es válido por sí solo; la central solo necesita enterarse. Rechazarlo detendría la bodega por un componente que no es suyo. |
| Transferencia (`POST /transfers`) | **Rechazar con 503** | Sin broker no se puede orquestar la Saga. Aceptarla dejaría al cliente esperando una operación entre dos bodegas que nadie ejecuta. El cliente reintenta y el estado queda en `FAILED` con el motivo. |
| Reporte (`POST /reports`) | **Rechazar con 503** | Es fácil de reintentar y no hay pérdida de datos. |

---

## ADR-005 — Read model en la central (CQRS) en vez de consultar a todas las bodegas

**Contexto.** `GET /global/inventory/{sku}` necesita la suma de todas las bodegas.

**Alternativas.** (A) Scatter-gather en cada request. (B) Read model alimentado por eventos.

**Decisión.** B. Un worker proyecta `INVENTORY_UPDATED` en `inventory_view`. A queda disponible en `/global/inventory/{sku}/live` solo para comparar.

| Criterio | A: consultar bodegas | B: read model |
|---|---|---|
| Latencia | la de la bodega más lenta (44 ms en el lab con 3 bodegas sanas) | una consulta local |
| Disponibilidad | si una bodega cae, la respuesta queda incompleta (F5: total 161 en vez de 181) | responde siempre; marca la bodega caída como `stale` |
| Consistencia | fuerte en el instante de la consulta | eventual (en el lab, ~1 s en condiciones normales) |
| Complejidad | baja | eventos, worker, idempotencia, orden |
| Acoplamiento | la central depende de cada bodega en cada request | la central solo depende de RabbitMQ |

**Consecuencias.**
- La respuesta declara `"consistency": "eventual"`.
- Un health poller (cada 10 s) marca `stale: true` y agrega una advertencia cuando una bodega no responde.
- Con el worker detenido, el read model se atrasa pero no pierde nada: los mensajes esperan en la cola (F3).

---

## ADR-006 — Saga orquestada para transferencias

**Contexto.** Transferir entre WH-001 y WH-002 toca dos bases sin transacción común, y las bodegas no tienen red entre sí.

**Alternativas.** (1) 2PC: no es viable entre servicios autónomos. (2) Saga coreografiada (las bodegas reaccionan a eventos de la otra). (3) Saga orquestada desde la central.

**Decisión.** Orquestada. La central es el único punto con red hacia todas las bodegas y deja el estado de cada transferencia visible en un solo lugar (`GET /transfers/{id}` con su historial).

Estados y compensaciones:

| Falla en | Estado final | Compensación |
|---|---|---|
| Antes de reservar / sin stock / sku inexistente | `FAILED` | ninguna (no se tocó nada) |
| Después de reservar (destino rechaza o no responde tras 3 reintentos) | `CANCELLED` | `RELEASE` de la reserva en origen |
| Después de recibir en destino (origen no confirma `TRANSFER_OUT`) | queda en `DESTINATION_RECEIVED` con error | no se compensa: las unidades ya llegaron; se reintenta con `/transfers/{id}/redeliver` |

**Consecuencias.**
- Cada paso lleva `Idempotency-Key` (`TR-x:reserve/in/out/release`). Reintentos, mensajes duplicados y reinicios del worker no duplican movimientos (comprobado en el lab).
- `TRANSFER_OUT` consume lo reservado: entre `SOURCE_RESERVED` y `COMPLETED` las unidades no están disponibles en origen.
- Riesgo aceptado: si el destino aplicó `TRANSFER_IN` pero la respuesta se perdió y después cae, la Saga compensa en origen y aparecen unidades de más. Se detecta con `GET /inventory/movements/by-key/TR-x:in` en una reconciliación.

---

## ADR-007 — Idempotencia persistente, reintentos acotados y DLQ

**Decisión.**
- Proyección: tabla `processed_events (event_id, consumer)` en la misma transacción que el cambio, más `movement_id` como versión para tolerar desorden.
- Bodega: `Idempotency-Key` con índice único.
- Reintentos solo para errores transitorios, 3 intentos con backoff de 1, 2 y 4 s. Los errores permanentes van directo a la DLQ (matriz completa en `docs/eventos.md`).
- `POST /admin/dlq/<cola>/replay` reinyecta los mensajes una vez corregida la causa.

**Consecuencias.**
- La idempotencia sobrevive a reinicios; antes era un `set()` en memoria que se perdía.
- El backoff bloquea el hilo consumidor mientras espera. Si el throughput lo exige, se reemplaza por colas de espera con TTL.

---

## ADR-008 — EC2 + Docker Compose con Nginx como balanceador, en vez de ECS/ALB

**Contexto.** AWS Academy: sin creación de roles IAM, créditos limitados y sesiones de 4 horas.

**Alternativas.** (1) ECS Fargate + ALB por bodega. (2) EC2 por bodega con Docker Compose y Nginx.

**Decisión.** Opción 2. Una EC2 t3.small por bodega y otra para la central. Cada bodega corre Nginx como LB frente a `API_REPLICAS` réplicas stateless, en round-robin.
- Nginx vuelve a resolver el DNS de Docker cada 5 s: las réplicas que se detienen o se crean entran y salen del pool sin reiniciarlo.
- Un fallo de conexión se reintenta en otra réplica.
- No hay expulsión pasiva por conteo (`max_fails=0`). En la prueba de carga, contar los timeouts por sobrecarga desactivó las 3 réplicas a la vez (ver `docs/pruebas.md` §3.4).

**Consecuencias.**
- (+) Barato, rápido de recrear, fácil de depurar por SSH y escalable por bodega (`API_REPLICAS`).
- (+) 3 réplicas toleran 1000 usuarios (2,9 % de errores) donde 1 réplica colapsa.
- (−) Con una réplica caída, ~1 de 40 requests recibe 502 en los primeros segundos, hasta que Nginx actualiza el pool: Nginx open source no tiene health checks activos. Un ALB con health check sobre `/health` lo resolvería.
- (−) El LB y las réplicas comparten la máquina (2 vCPU, techo medido de ~530 req/s con Redis): escala vertical por bodega. El paso siguiente es un ALB + Auto Scaling Group por bodega.
- (−) PostgreSQL y RabbitMQ corren en contenedores. En producción se usarían RDS y Amazon MQ.

---

## ADR-009 — Batch a S3 y Lambda vía EventBridge

**Decisión.**
- El batch diario (cron 23:00 UTC en la central, o `POST /reports`) escribe el reporte y los snapshots por bodega en S3, con claves que dependen solo de la fecha: es reejecutable y cada ejecución queda en `report_jobs`.
- Una Lambda valida cada reporte nuevo en `reports/`, guarda `metadata/...meta.json` y avisa a la central.
- El disparo es S3 → EventBridge → Lambda: la notificación directa S3 → Lambda no entregó eventos en el Learner Lab.
- El bucket se crea con CloudFormation porque una SCP del lab bloquea la lectura de Object Lock que hace `aws_s3_bucket`.

| | Worker (proyección, Saga) | Batch (reporte diario) | Lambda (validador) |
|---|---|---|---|
| Ejecución | continua | programada | por evento |
| Latencia | ~1 s | hasta el próximo cron | segundos |
| Escala | réplicas que controlamos | una ejecución por día | administrada por AWS |
| Costo en reposo | la EC2 siempre encendida | nulo fuera de ejecución | nulo |
| Uso adecuado | flujo constante de eventos | procesar mucho volumen de una vez | reacciones cortas y esporádicas |

---

## ADR-010 — Modelo de seguridad, aislamiento de red y gestión de secretos

**Contexto.** El proyecto debe definir el manejo de credenciales, aislamiento perimetral, control de accesos y prevención de vectores comunes de vulnerabilidad (inyección SQL, exposición de datos, sobrecarga).

**Decisión.**
1. **Gestión de secretos fuera de Git:**
   - Contraseñas de bases de datos (`DB_PASSWORD`, `CENTRAL_DB_PASSWORD`) y RabbitMQ se generan de forma aleatoria mediante `openssl rand -hex 16` durante el primer despliegue en `.deploy.env`.
   - `.deploy.env` está explícitamente excluido en `.gitignore` con permisos estrictos (`chmod 600`).
   - Ninguna credencial, clave de API ni secreto vive en el repositorio.
2. **Aislamiento perimetral y mínimo privilegio en red:**
   - La arquitectura es Hub-and-Spoke estricta: las bodegas únicamente tienen peering con la central y carecen de conectividad entre sí.
   - Los puertos de datos sensibles (PostgreSQL `5432` y RabbitMQ AMQP `5672`) solo aceptan tráfico interno dentro de la red corporativa/VPC (`10.0.0.0/8`). No están expuestos a Internet.
   - S3 tiene todas las opciones de bloqueo de acceso público activadas (`BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, `RestrictPublicBuckets`).
3. **Credenciales en la nube:**
   - Acceso a S3 y EventBridge mediante el rol IAM asignado a la instancia (`LabInstanceProfile` / IMDSv2). No se usan llaves estáticas (`AWS_ACCESS_KEY_ID`).
4. **Validación y mitigación de inyección:**
   - Validación estricta de esquemas de entrada en APIs mediante Pydantic y serialización controlada.
   - Todas las consultas a base de datos utilizan el ORM de SQLAlchemy con consultas parametrizadas, evitando inyecciones SQL.
   - Restricciones a nivel de base de datos (`CHECK (quantity >= 0)`).

**Consecuencias y trade-offs del laboratorio:**
- (+) Alta seguridad en el plano de red e infraestructura sin credenciales filtrables.
- (−) **Autenticación en endpoints `/admin` y puerto 8080:** En este entorno de laboratorio, los endpoints de inyección de fallos (`/admin/inject/*`) y la API central no implementan tokens HTTP Bearer / Basic Auth para facilitar las pruebas automáticas, las suites de k6 y los scripts de curl documentados.
- **Camino a producción:**
  - Incorporar autenticación mediante tokens JWT (OAuth2 / OIDC) en la API Central y en cada bodega.
  - Colocar la API central detrás de un Application Load Balancer con certificado HTTPS (AWS Certificate Manager) y AWS WAF.
  - Proteger los endpoints `/admin` mediante red privada (VPC Endpoint) o roles de administración específicos (RBAC).

---

## Pregunta final: 100 bodegas con cargas distintas

Escalarían de forma independiente:

1. **Cada bodega (API + Redis + PostgreSQL)**, según su propia carga. Se ajustan `API_REPLICAS`, el tamaño o la cantidad de instancias solo donde hace falta. Medido en `docs/pruebas.md`:
   - Con Redis, PostgreSQL queda en 0,1 % de CPU y el límite es la CPU de las APIs (~530 req/s por t3.small).
   - WH-002 (800 req/s) necesita aproximadamente el doble de capacidad.
   - WH-001 y WH-003 siguieron en milisegundos mientras WH-002 estaba saturada.
2. **RabbitMQ y el worker de proyección de la central**, según el volumen total de eventos: la suma de las 100 bodegas. Se agregan consumidores a `central.projection`; la proyección es idempotente y tolera desorden.
3. **El read model de la central**, según las consultas globales; admite réplicas de lectura.

No hace falta escalar: el batch (una ejecución diaria) ni la Lambda (AWS la escala sola).

Lo que habría que cambiar:
- La red hub-and-spoke con peering tiene límite de peerings por VPC: con 100 bodegas se pasa a Transit Gateway.
- El health poller secuencial de la central tarda demasiado con 100 bodegas: hay que paralelizarlo o reemplazarlo por heartbeats.
