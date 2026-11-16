from tests.conftest import move


def test_crud_productos(client, product):
    pid = product["id"]
    assert client.get(f"/products/{pid}").json()["sku"] == "P-001"
    assert client.get("/products/by-sku/P-001").json()["id"] == pid
    assert client.put(f"/products/{pid}", json={"name": "Laptop Pro"}).json()["name"] == "Laptop Pro"
    assert client.get(f"/inventory/{pid}").json()["quantity"] == 0
    assert client.delete(f"/products/{pid}").status_code == 204
    assert client.get(f"/products/{pid}").status_code == 404


def test_sku_duplicado(client, product):
    r = client.post("/products", json={"sku": "P-001", "name": "Otro", "unit": "UNIDAD"})
    assert r.status_code == 409


def test_no_elimina_producto_con_stock(client, product):
    move(client, product["id"], "RECEIPT", 1)
    assert client.delete(f"/products/{product['id']}").status_code == 409


def test_correlation_id_se_propaga_y_genera(client):
    r = client.get("/products", headers={"X-Correlation-ID": "COR-TEST-1"})
    assert r.headers["X-Correlation-ID"] == "COR-TEST-1"
    assert client.get("/products").headers["X-Correlation-ID"].startswith("COR-")


def test_health_y_metrics(client):
    assert client.get("/health").json()["status"] == "ok"
    m = client.get("/metrics").json()
    assert m["api"]["requests_total"] >= 1
