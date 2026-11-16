# Fase 11 — Observabilidad y Load Testing

## Objetivo

Medir el sistema en lugar de asumir que funciona correctamente.

## Correlation ID

Ejemplo:

```text
COR-20260928-001
```

Debe acompañar:

```text
HTTP
 |
 v
API
 |
 v
RabbitMQ
 |
 v
Worker
 |
 v
DB
```

## Logs

Ejemplo:

```json
{
  "service": "transfer-worker",
  "level": "INFO",
  "event": "transfer_completed",
  "transfer_id": "TR-001",
  "correlation_id": "COR-001"
}
```

## Métricas

API:

- RPS;
- P50;
- P95;
- P99;
- error rate.

Redis:

- hit ratio;
- misses;
- memory.

RabbitMQ:

- queue depth;
- processing rate;
- retries;
- DLQ.

DB:

- latency;
- active connections;
- locks.

## Load testing

Realizar pruebas con:

```text
100
500
1000
5000
```

usuarios/conexiones simuladas.

Comparar:

```text
1 API instance
3 API instances
```

y:

```text
Redis OFF
Redis ON
```

## Entregable

Informe con:

1. escenario;
2. carga;
3. arquitectura;
4. métricas;
5. resultados;
6. cuello de botella;
7. hipótesis;
8. evidencia;
9. propuesta de mejora.
