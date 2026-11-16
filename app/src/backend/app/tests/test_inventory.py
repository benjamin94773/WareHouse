from tests.conftest import move


def stock(client, pid):
    return client.get(f"/inventory/{pid}").json()


def test_salida_no_deja_inventario_negativo(client, product):
    assert move(client, product["id"], "RECEIPT", 10).status_code == 201
    assert move(client, product["id"], "SHIPMENT", 4).status_code == 201
    assert stock(client, product["id"])["quantity"] == 6
    r = move(client, product["id"], "SHIPMENT", 15)
    assert r.status_code == 400
    assert stock(client, product["id"])["quantity"] == 6


def test_movimiento_rechazado_no_deja_rastro(client, product):
    move(client, product["id"], "SHIPMENT", 1)
    assert client.get(f"/inventory/{product['id']}/movements").json() == []


def test_ajuste_admite_negativos_sin_bajar_de_cero(client, product):
    move(client, product["id"], "RECEIPT", 5)
    assert move(client, product["id"], "ADJUSTMENT", -2).status_code == 201
    assert move(client, product["id"], "ADJUSTMENT", -9).status_code == 400
    assert stock(client, product["id"])["quantity"] == 3


def test_reserva_y_liberacion(client, product):
    move(client, product["id"], "RECEIPT", 10)
    move(client, product["id"], "RESERVATION", 4)
    s = stock(client, product["id"])
    assert (s["quantity"], s["reserved_quantity"]) == (6, 4)
    move(client, product["id"], "RELEASE", 4)
    s = stock(client, product["id"])
    assert (s["quantity"], s["reserved_quantity"]) == (10, 0)


def test_validaciones(client, product):
    assert move(client, product["id"], "INVALIDO", 1).status_code == 422
    assert move(client, product["id"], "RECEIPT", 0).status_code == 422
    assert move(client, product["id"], "RECEIPT", -1).status_code == 422
    assert move(client, 999, "RECEIPT", 1).status_code == 404


def test_movimiento_genera_evento_en_outbox(client, product):
    move(client, product["id"], "RECEIPT", 3)
    events = client.get("/inventory/outbox/audit").json()
    assert len(events) == 1 and events[0]["status"] == "PENDING"


def test_contrato_del_evento(client, product):
    move(client, product["id"], "RECEIPT", 5)
    move(client, product["id"], "RESERVATION", 2)
    ev = client.get("/inventory/outbox/audit").json()[0]["payload"]  # el más reciente
    assert ev["event_type"] == "INVENTORY_UPDATED" and ev["event_version"] == 1
    assert ev["source"] == "warehouse-WH-TEST" and ev["correlation_id"].startswith("COR-")
    p = ev["payload"]
    assert (p["sku"], p["movement_type"], p["quantity"], p["reserved_quantity"]) == ("P-001", "RESERVATION", 3, 2)


def test_idempotency_key_no_duplica_el_movimiento(client, product):
    body = {"product_id": product["id"], "type": "RECEIPT", "quantity": 5}
    r1 = client.post("/inventory/movements", json=body, headers={"Idempotency-Key": "TR-1:in"})
    r2 = client.post("/inventory/movements", json=body, headers={"Idempotency-Key": "TR-1:in"})
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json()["id"] == r2.json()["id"]
    assert stock(client, product["id"])["quantity"] == 5
    assert client.get("/inventory/movements/by-key/TR-1:in").status_code == 200
    assert client.get("/inventory/movements/by-key/otra").status_code == 404


def test_transfer_out_consume_lo_reservado(client, product):
    move(client, product["id"], "RECEIPT", 10)
    assert move(client, product["id"], "TRANSFER_OUT", 3).status_code == 400  # sin reserva
    move(client, product["id"], "RESERVATION", 3)
    assert move(client, product["id"], "TRANSFER_OUT", 3).status_code == 201
    s = stock(client, product["id"])
    assert (s["quantity"], s["reserved_quantity"]) == (7, 0)
