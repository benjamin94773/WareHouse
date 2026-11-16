# Fase 7 — Plataforma Central y CQRS

## Objetivo

Construir una visión consolidada de todas las bodegas sin consultar todas las bases en cada request.

## Problema

```text
WH1 = 100
WH2 = 50
WH3 = 80
WH4 = 20
```

La central necesita responder:

```http
GET /global/inventory/P-001
```

## Solución

Construir un Read Model.

```text
Warehouse Events
       |
       v
   RabbitMQ
       |
       v
Projection Worker
       |
       v
Central Read DB
```

## CQRS

### Command side

```text
API
 |
 v
Operational DB
```

### Query side

```text
Events
 |
 v
Projection
 |
 v
Read Model
```

## Concepto clave

El Read Model puede estar temporalmente desactualizado.

Eso es consistencia eventual.

## Ejercicio

Comparar:

### Alternativa A

```text
Central API
 |
 +--> WH1
 +--> WH2
 +--> WH3
 +--> WH4
```

### Alternativa B

```text
Events
 |
 v
Central Read Model
 |
 v
Central API
```

Documentar:

- latencia;
- disponibilidad;
- consistencia;
- complejidad;
- dependencia de servicios.
