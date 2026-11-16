from datetime import timedelta

from fastapi.testclient import TestClient

from consumers import project_inventory_event
from db import SessionLocal, WarehouseStatus, now
from main import app
from tests.conftest import event

client = TestClient(app)  # sin "with": no arranca el health poller


def set_status(wh, healthy, ago_s=0):
    with SessionLocal() as db:
        db.merge(WarehouseStatus(warehouse_id=wh, healthy=healthy, last_health_ok_at=now() - timedelta(seconds=ago_s)))
        db.commit()


def test_inventario_global_suma_bodegas_y_marca_desactualizada():
    project_inventory_event(event("E1", wh="WH-001", qty=100))
    project_inventory_event(event("E2", wh="WH-002", qty=50))
    set_status("WH-001", True)
    set_status("WH-002", False, ago_s=120)  # WH-002 caída

    r = client.get("/global/inventory/P-001").json()
    assert r["total_quantity"] == 150 and r["consistency"] == "eventual"
    stale = {w["warehouse_id"]: w["stale"] for w in r["warehouses"]}
    assert stale == {"WH-001": False, "WH-002": True}
    assert any("WH-002" in w for w in r["warnings"])


def test_sku_sin_datos():
    assert client.get("/global/inventory/NOPE").status_code == 404


def test_reporte_de_eventos_por_bodega():
    project_inventory_event(event("E1", wh="WH-001"))
    r = client.get("/reports/events-by-warehouse").json()
    assert r["warehouses_summary"]["WH-001"]["by_type"] == {"RECEIPT": 1}
