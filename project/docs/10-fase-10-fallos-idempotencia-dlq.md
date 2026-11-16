# Fase 10 — Resiliencia

## Objetivo

Diseñar el sistema asumiendo que los componentes pueden fallar.

## Fallos mínimos

### Redis

Debe existir fallback hacia PostgreSQL.

### RabbitMQ

Definir estrategia para:

- retry;
- persistencia;
- recuperación.

### Worker

Los mensajes no procesados deben permanecer disponibles.

### Mensajes duplicados

Utilizar:

```text
event_id
```

y registro de eventos procesados.

### Mensajes inválidos

Enviar a:

```text
DLQ
```

## Retry

```text
Attempt 1
   |
   X
Attempt 2
   |
   X
Attempt 3
   |
   X
DLQ
```

## Ejercicio

Crear una matriz:

| Error | ¿Retry? | ¿DLQ? | ¿Compensación? |
|---|---|---|---|
| Timeout | Sí | Después de varios intentos | Depende |
| JSON inválido | No | Sí | No |
| DB temporalmente caída | Sí | Después de límite | Depende |
| Producto inexistente | No | Sí | No |

El estudiante debe justificar cada decisión.
