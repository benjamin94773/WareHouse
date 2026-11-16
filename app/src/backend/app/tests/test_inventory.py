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
