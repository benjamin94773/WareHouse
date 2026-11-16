import os
import sys

os.environ.setdefault("CENTRAL_DATABASE_URL", "sqlite:///./central_test.db")
os.environ.setdefault("WAREHOUSES", "WH-001=http://wh1.invalid,WH-002=http://wh2.invalid")
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path[:0] = [ROOT, os.path.join(ROOT, "..")]  # central/ y app/src/ (paquete shared)

import pytest
from db import Base, engine


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def event(event_id="E1", wh="WH-001", sku="P-001", movement_id=1, qty=10, reserved=0, mtype="RECEIPT"):
    return {"event_id": event_id, "event_type": "INVENTORY_UPDATED", "event_version": 1,
            "occurred_at": "2026-11-15T10:00:00+00:00", "correlation_id": "COR-T",
            "payload": {"warehouse_id": wh, "sku": sku, "product_id": 1, "product_name": "Laptop",
                        "movement_id": movement_id, "movement_type": mtype, "movement_quantity": qty,
                        "quantity": qty, "reserved_quantity": reserved}}
