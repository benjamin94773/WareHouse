import json
from types import SimpleNamespace

import pytest

import consumers
from consumers import PermanentError, process_message, project_inventory_event
from db import EventLog, InventoryView, SessionLocal
from tests.conftest import event


def view(wh="WH-001", sku="P-001"):
    with SessionLocal() as db:
        return db.get(InventoryView, (wh, sku))


def test_evento_duplicado_no_se_aplica_dos_veces():
    project_inventory_event(event("E1"))
    project_inventory_event(event("E1"))
    with SessionLocal() as db:
        assert db.query(EventLog).count() == 1
    assert view().quantity == 10


def test_evento_fuera_de_orden_no_retrocede_el_balance():
    project_inventory_event(event("E2", movement_id=2, qty=7))
    project_inventory_event(event("E1", movement_id=1, qty=10))
    assert (view().quantity, view().version) == (7, 2)


@pytest.mark.parametrize("bad", [{"event_type": "X"}, {"event_id": "E", "event_type": "INVENTORY_UPDATED", "payload": {}}])
def test_evento_invalido_es_error_permanente(bad):
    with pytest.raises(PermanentError):
        project_inventory_event(bad)


class FakeChannel:
    def __init__(self):
        self.acked, self.nacked, self.published = [], [], []

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_nack(self, tag, requeue):
        self.nacked.append((tag, requeue))

    def basic_publish(self, exchange, key, body, props):
        self.published.append(props.headers)


def run(body, handler, retries=0):
    ch = FakeChannel()
    props = SimpleNamespace(headers={"x-retries": retries}, correlation_id="COR-T")
    process_message(ch, SimpleNamespace(delivery_tag=1), props, body, "central.projection", handler)
    return ch


def test_json_invalido_va_directo_a_dlq():
    ch = run(b"{no json", project_inventory_event)
    assert ch.nacked == [(1, False)] and not ch.published


def test_error_transitorio_se_reintenta_y_luego_va_a_dlq(monkeypatch):
    monkeypatch.setattr(consumers.time, "sleep", lambda s: None)

    def boom(msg):
        raise ConnectionError("db caida")

    body = json.dumps(event()).encode()
    ch = run(body, boom, retries=0)
    assert ch.acked == [1] and ch.published[0]["x-retries"] == 1
    ch = run(body, boom, retries=3)
    assert ch.nacked == [(1, False)]
