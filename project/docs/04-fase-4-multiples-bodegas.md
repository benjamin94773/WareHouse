# Fase 4 — Múltiples Bodegas

## Objetivo

Convertir la aplicación en un sistema distribuido.

## Arquitectura

```text
             Central
                |
       +--------+--------+
       |        |        |
      WH1      WH2      WH3
       |        |        |
      API      API      API
       |        |        |
      DB       DB       DB
       |        |        |
    Redis    Redis    Redis
```

## Reglas

Cada bodega debe tener:

- API;
- PostgreSQL;
- Redis.

Las bodegas no deben compartir directamente sus bases operacionales.

## Objetivos pedagógicos

Demostrar:

- aislamiento;
- autonomía;
- fallos parciales;
- escalamiento independiente;
- particionamiento por dominio.

## Ejercicio

Configurar:

```text
WH-001
WH-002
WH-003
```

y demostrar que:

```text
WH-002 DOWN
```

no impide:

```text
WH-001
WH-003
```

seguir funcionando.

## Carga

Simular:

```text
WH-001 = 50 req/s
WH-002 = 800 req/s
WH-003 = 20 req/s
```

Discutir por qué no sería deseable obligar a todas las bodegas a escalar de la misma manera.
