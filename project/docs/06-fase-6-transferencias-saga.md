# Fase 6 — Transferencias y Saga

## Objetivo

Resolver una operación que involucra dos dominios independientes.

## Caso

```text
WH-001 P-001 = 100
WH-002 P-001 = 20
```

Transferir:

```text
30 unidades
```

Resultado:

```text
WH-001 = 70
WH-002 = 50
```

## Problema

No existe una transacción SQL única entre:

```text
DB-WH-001
DB-WH-002
```

## Saga

```text
REQUESTED
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

En caso de fallo:

```text
COMPENSATING
    |
    v
RESERVATION_RELEASED
```

## API

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

## Idempotencia

El worker debe poder recibir:

```text
TR-001
TR-001
```

sin duplicar la transferencia.

## Experimentos de fallo

1. fallar antes de reservar;
2. fallar después de reservar;
3. destino caído;
4. mensaje duplicado;
5. timeout;
6. worker reiniciado.

## Entregable

Diagrama de estados y explicación de cada compensación.
