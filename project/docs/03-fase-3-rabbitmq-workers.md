# Fase 2 — Redis y Caching

## Objetivo

Reducir la cantidad de lecturas repetitivas sobre PostgreSQL.

## Arquitectura

```text
Client
  |
  v
API
  |
  v
Redis
 /  \
HIT MISS
     |
     v
 PostgreSQL
     |
     v
   Redis
```

## Implementación

Utilizar Cache Aside.

```python
value = redis.get(key)

if value:
    return value

value = db.get_inventory(product_id)

redis.set(key, value, ex=30)

return value
```

## Cache key

```text
warehouse:WH-001:inventory:P-001
```

## Invalidación

Implementar:

1. TTL.
2. Invalidación explícita.

Después de modificar inventario:

```text
DB UPDATE
   |
   v
DELETE CACHE
```

## Experimento

Comparar:

```text
PostgreSQL solamente
```

contra:

```text
PostgreSQL + Redis
```

Medir:

- latencia;
- requests/sec;
- CPU;
- consultas SQL;
- cache hit ratio.

## Preguntas

- ¿Qué ocurre si Redis se cae?
- ¿Qué ocurre si el cache está obsoleto?
- ¿Qué ocurre si dos requests actualizan el mismo producto?
- ¿Qué información nunca debería depender únicamente de Redis?
