# Proyecto Integrador — Índice

## Documento principal

- [README — Proyecto Integrador](README.md)
- [Arquitectura final](14-arquitectura-final.md)

## Fases

1. [Fase 1 — Bodega + API + PostgreSQL](01-fase-1-bodega-api-postgresql.md)
2. [Fase 2 — Redis + Cache](02-fase-2-redis-cache.md)
3. [Fase 3 — RabbitMQ + Workers](03-fase-3-rabbitmq-workers.md)
4. [Fase 4 — Múltiples Bodegas](04-fase-4-multiples-bodegas.md)
5. [Fase 5 — Load Balancing](05-fase-5-load-balancing.md)
6. [Fase 6 — Transferencias + Saga](06-fase-6-transferencias-saga.md)
7. [Fase 7 — Central + CQRS](07-fase-7-central-cqrs.md)
8. [Fase 8 — S3 + Batch](08-fase-8-s3-batch.md)
9. [Fase 9 — Lambda](09-fase-9-lambda.md)
10. [Fase 10 — Fallos + Idempotencia + DLQ](10-fase-10-fallos-idempotencia-dlq.md)
11. [Fase 11 — Observabilidad + Load Testing](11-fase-11-observabilidad-load-testing.md)
12. [Fase 12 — IoT](12-fase-12-iot.md)

## Entrega

- [Guía de entrega y evaluación](13-guia-de-entrega-y-evaluacion.md)

---

## Ruta pedagógica

```text
API + DB
   ↓
Redis
   ↓
RabbitMQ
   ↓
Múltiples bodegas
   ↓
Load Balancer
   ↓
Saga
   ↓
CQRS
   ↓
S3 + Batch
   ↓
Lambda
   ↓
Resiliencia
   ↓
Observabilidad
   ↓
IoT
```

La recomendación es que cada fase tenga una entrega funcional antes de iniciar la siguiente.
