"""
Cache Aside sobre Redis. Redis es una optimización, nunca la fuente de verdad:
si falla, todas las operaciones degradan en silencio a PostgreSQL.
"""
import json
import logging
import time

import redis

from app.config import settings

logger = logging.getLogger("cache")

_client = redis.Redis.from_url(
    settings.REDIS_URL,
    socket_timeout=0.2,          # Redis caído no debe sumar latencia apreciable
    socket_connect_timeout=0.2,
)
_down_until = 0.0  # tras un fallo se omite Redis unos segundos en vez de reintentar en cada request
RETRY_AFTER_S = 5


def inventory_key(product_id: int) -> str:
    # El id de bodega en la clave evita colisiones si varias bodegas comparten un Redis
    return f"warehouse:{settings.WAREHOUSE_ID}:inventory:{product_id}"


def _call(fn, *args):
    global _down_until
    if not settings.CACHE_ENABLED or time.monotonic() < _down_until:
        return None
    try:
        return fn(*args)
    except redis.RedisError as e:
        _down_until = time.monotonic() + RETRY_AFTER_S
        logger.warning("redis_unavailable fallback=postgres error=%s", e)
        return None


def get_json(key: str):
    raw = _call(_client.get, key)
    return json.loads(raw) if raw else None


def set_json(key: str, value: dict) -> None:
    _call(_client.set, key, json.dumps(value, default=str), settings.CACHE_TTL_SECONDS)


def delete(key: str) -> None:
    _call(_client.delete, key)
