import urllib.error

import pytest

import saga
import warehouses
from db import SessionLocal, Transfer
from warehouses import WarehouseError


class FakeWarehouse:
    """Bodega en memoria con las reglas de la API real (idempotencia, reservas)."""

    def __init__(self):
        self.products, self.stock, self.keys, self.down = {}, {}, {}, False

    def handle(self, method, path, data, key):
        if self.down:
            raise urllib.error.URLError("connection refused")
        if path.startswith("/products/by-sku/"):
            sku = path.rsplit("/", 1)[1]
            if sku not in self.products:
                raise WarehouseError(404, "no existe")
            return self.products[sku]
        if path == "/products":
            pid = len(self.products) + 1
            self.products[data["sku"]] = {"id": pid, **data}
            self.stock[pid] = [0, 0]
            return self.products[data["sku"]]
        if path == "/inventory/movements":
            if key in self.keys:
                return self.keys[key]
            q, r = self.stock[data["product_id"]]
            n, t = data["quantity"], data["type"]
            if t == "RESERVATION":
                if q < n:
                    raise WarehouseError(400, "Stock insuficiente")
                q, r = q - n, r + n
            elif t == "RELEASE":
                q, r = q + n, r - n
            elif t == "TRANSFER_OUT":
                r -= n
            elif t == "TRANSFER_IN":
                q += n
            self.stock[data["product_id"]] = [q, r]
            self.keys[key] = {"id": len(self.keys) + 1}
            return self.keys[key]
        raise AssertionError(path)


@pytest.fixture()
def whs(monkeypatch):
    fakes = {"WH-001": FakeWarehouse(), "WH-002": FakeWarehouse()}
    fakes["WH-001"].handle("POST", "/products", {"sku": "P-001", "name": "Laptop", "description": None, "category": None, "unit": "U"}, None)
    fakes["WH-001"].stock[1] = [100, 0]

    def request(wh, method, path, data=None, timeout=5, headers=None):
        return 200, fakes[wh].handle(method, path, data, (headers or {}).get("Idempotency-Key"))

    monkeypatch.setattr(warehouses, "request", request)
    return fakes


def new_transfer(qty=30, **kw):
    with SessionLocal() as db:
        db.add(Transfer(id="TR-1", source="WH-001", destination="WH-002", sku="P-001", quantity=qty, status="REQUESTED", history=[], **kw))
        db.commit()


def status():
    return saga.load("TR-1").status


def test_transferencia_completa(whs):
    new_transfer()
    saga.handle_transfer({"transfer_id": "TR-1"})
    assert status() == "COMPLETED"
    assert whs["WH-001"].stock[1] == [70, 0] and whs["WH-002"].stock[1] == [30, 0]
    assert [h["status"] for h in saga.load("TR-1").history] == [
        "RESERVING_SOURCE", "SOURCE_RESERVED", "IN_TRANSIT", "DESTINATION_RECEIVED", "COMPLETED"]


def test_comando_duplicado_no_repite_la_transferencia(whs):
    new_transfer()
    saga.handle_transfer({"transfer_id": "TR-1"})
    saga.handle_transfer({"transfer_id": "TR-1"})
    assert whs["WH-001"].stock[1] == [70, 0] and whs["WH-002"].stock[1] == [30, 0]


def test_sin_stock_falla_sin_compensar(whs):
    new_transfer(qty=500)
    saga.handle_transfer({"transfer_id": "TR-1"})
    assert status() == "FAILED" and whs["WH-001"].stock[1] == [100, 0]


def test_fallo_despues_de_reservar_compensa(whs):
    new_transfer(simulate_failure="after_reserve")
    saga.handle_transfer({"transfer_id": "TR-1"})
    assert status() == "CANCELLED" and whs["WH-001"].stock[1] == [100, 0]


def test_destino_caido_reintenta_y_luego_compensa(whs):
    new_transfer()
    whs["WH-002"].down = True
    with pytest.raises(urllib.error.URLError):  # transitorio: el consumidor reintenta
        saga.handle_transfer({"transfer_id": "TR-1"})
    assert status() == "IN_TRANSIT" and whs["WH-001"].stock[1] == [70, 30]
    saga.on_transfer_dead({"transfer_id": "TR-1"}, "reintentos agotados")
    assert status() == "CANCELLED" and whs["WH-001"].stock[1] == [100, 0]


def test_reinicio_del_worker_retoma_sin_duplicar(whs):
    new_transfer()
    whs["WH-002"].down = True
    with pytest.raises(urllib.error.URLError):
        saga.handle_transfer({"transfer_id": "TR-1"})
    whs["WH-002"].down = False  # vuelve la bodega / el worker reinicia y recibe el mensaje de nuevo
    saga.handle_transfer({"transfer_id": "TR-1"})
    assert status() == "COMPLETED"
    assert whs["WH-001"].stock[1] == [70, 0] and whs["WH-002"].stock[1] == [30, 0]
