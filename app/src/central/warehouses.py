"""Cliente HTTP hacia las APIs de bodega (vía su load balancer). Propaga el correlation_id."""
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from shared.observability import CORRELATION_HEADER, correlation_id


def warehouse_urls() -> dict:
    """WAREHOUSES="WH-001=http://10.1.1.10,WH-002=http://10.2.1.10" -> {"WH-001": "http://10.1.1.10", ...}"""
    raw = os.getenv("WAREHOUSES", "")
    return dict(item.split("=", 1) for item in raw.split(",") if "=" in item)


class WarehouseError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body}")
        self.status, self.body = status, body


def request(warehouse_id, method, path, data=None, timeout=5, headers=None):
    """Devuelve (status, json). Lanza WarehouseError en 4xx/5xx y URLError/TimeoutError si no responde."""
    base = warehouse_urls().get(warehouse_id)
    if not base:
        raise WarehouseError(404, f"Bodega {warehouse_id} no configurada")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    if correlation_id.get():
        hdrs[CORRELATION_HEADER] = correlation_id.get()
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base + path, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raise WarehouseError(e.code, e.read().decode(errors="replace")) from None


def live_inventory(sku: str) -> dict:
    """Alternativa A (scatter-gather): consulta todas las bodegas en paralelo en cada request."""
    def one(wh):
        start = time.perf_counter()
        try:
            _, product = request(wh, "GET", f"/products/by-sku/{sku}", timeout=3)
            _, inv = request(wh, "GET", f"/inventory/{product['id']}", timeout=3)
            result = {"quantity": inv["quantity"], "reserved_quantity": inv["reserved_quantity"]}
        except WarehouseError as e:
            result = {"error": "sku no existe" if e.status == 404 else str(e)}
        except Exception as e:
            result = {"error": f"bodega inaccesible: {e}"}
        return wh, {**result, "latency_ms": round((time.perf_counter() - start) * 1000, 1)}

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(pool.map(one, warehouse_urls()))
    return {
        "sku": sku,
        "strategy": "scatter-gather (consulta directa a cada bodega)",
        "total_quantity": sum(r.get("quantity", 0) for r in results.values()),
        "complete": all("error" not in r for r in results.values()),
        "total_latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "warehouses": results,
    }
