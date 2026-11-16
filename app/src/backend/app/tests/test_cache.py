import redis

from app import cache
from tests.conftest import move


class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, k):
        return self.data.get(k)

    def set(self, k, v, ex=None):
        self.data[k] = v

    def delete(self, k):
        self.data.pop(k, None)


class DownRedis:
    def __getattr__(self, name):
        def fail(*a, **kw):
            raise redis.ConnectionError("redis caido")
        return fail


def test_cache_aside_hit_miss_e_invalidacion(client, product, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_client", fake)
    pid = product["id"]
    move(client, pid, "RECEIPT", 10)

    r1 = client.get(f"/inventory/{pid}")
    r2 = client.get(f"/inventory/{pid}")
    assert (r1.headers["X-Cache"], r2.headers["X-Cache"]) == ("MISS", "HIT")
    assert cache.inventory_key(pid) == f"warehouse:WH-TEST:inventory:{pid}"

    move(client, pid, "SHIPMENT", 4)  # debe invalidar la clave
    r3 = client.get(f"/inventory/{pid}")
    assert r3.headers["X-Cache"] == "MISS" and r3.json()["quantity"] == 6


def test_redis_caido_usa_postgres(client, product, monkeypatch):
    monkeypatch.setattr(cache, "_client", DownRedis())
    monkeypatch.setattr(cache, "_down_until", 0.0)
    move(client, product["id"], "RECEIPT", 7)
    r = client.get(f"/inventory/{product['id']}")
    assert r.status_code == 200 and r.json()["quantity"] == 7
