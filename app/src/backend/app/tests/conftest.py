import os
import sys

# Base SQLite en memoria compartida: las pruebas no necesitan PostgreSQL ni RabbitMQ
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("WAREHOUSE_ID", "WH-TEST")
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path[:0] = [ROOT, os.path.join(ROOT, "..", "..")]  # app/ y app/src/ (paquete shared)

import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from main import app
    return TestClient(app)  # sin "with": no arranca hilos de fondo


@pytest.fixture()
def product(client):
    r = client.post("/products", json={"sku": "P-001", "name": "Laptop", "unit": "UNIDAD"})
    assert r.status_code == 201, r.text
    return r.json()


def move(client, product_id, type_, qty):
    return client.post("/inventory/movements", json={"product_id": product_id, "type": type_, "quantity": qty, "reference": "test"})
