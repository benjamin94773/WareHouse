# Guía de Entrega y Evaluación

## Entregables finales

### 1. Código

Repositorio Git con:

```text
services/
infrastructure/
tests/
scripts/
docs/
```

### 2. Arquitectura

Diagrama actualizado de la solución final.

### 3. ADRs

Cada decisión importante debe documentarse.

Formato:

```text
# ADR-001 — Uso de Redis

## Contexto

...

## Alternativas

...

## Decisión

...

## Consecuencias

...
```

### 4. Eventos

Documentar contratos.

### 5. Pruebas

Incluir evidencia de:

- unit tests;
- integration tests;
- load tests;
- failure tests.

### 6. AWS

Documentar recursos utilizados.

### 7. Terraform

La infraestructura debe poder reconstruirse.

---

# Evaluación conceptual

El equipo debe poder defender:

- límites de cada dominio;
- modelo de datos;
- decisiones de caché;
- estrategia de eventos;
- consistencia;
- idempotencia;
- Saga;
- CQRS;
- escalamiento;
- observabilidad;
- resiliencia;
- uso de AWS.

---

# Pregunta final

Cada equipo debe responder:

> Si la plataforma tuviera que atender 100 bodegas y cada bodega tuviera una carga diferente, ¿qué componentes escalarían independientemente y por qué?

La respuesta debe estar soportada por:

- arquitectura;
- métricas;
- pruebas;
- decisiones técnicas.
