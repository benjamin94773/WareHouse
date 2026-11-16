# Fase 5 — Load Balancing y Escalamiento

## Objetivo

Permitir múltiples instancias de una misma API.

```text
Load Balancer
      |
 +----+----+
 |    |    |
API1 API2 API3
 |    |    |
 +----+----+
      |
    Redis
      |
 PostgreSQL
```

## Requisitos

Las APIs deben ser stateless.

No almacenar información crítica únicamente en memoria local.

## Health check

```http
GET /health
```

## Experimentos

### Experimento 1

```text
1 instancia
```

Medir throughput y latencia.

### Experimento 2

```text
3 instancias
```

Repetir mediciones.

### Experimento 3

Apagar una instancia.

Verificar que el sistema continúe atendiendo requests.

## Preguntas

- ¿Qué ocurre si Redis es local de cada instancia?
- ¿Por qué puede ser problemático?
- ¿Dónde debería vivir el estado compartido?
- ¿Qué significa que una API sea stateless?
