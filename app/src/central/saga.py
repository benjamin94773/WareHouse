"""
Saga orquestada de transferencias entre bodegas (no existe una transacción SQL entre dos bases).

  REQUESTED -> RESERVING_SOURCE -> SOURCE_RESERVED -> IN_TRANSIT -> DESTINATION_RECEIVED -> COMPLETED
                      |                   |                |
                      v                   +-------+--------+
                   FAILED                         v
       (sin stock / sku inexistente:       COMPENSATING -> CANCELLED
        no hay nada que compensar)         (RELEASE de la reserva en origen)

- Cada paso usa un Idempotency-Key (TR-x:reserve, :in, :out, :release): reintentar o recibir el
  comando dos veces no duplica movimientos.
- El estado se guarda antes de avanzar: si el worker reinicia, el comando vuelve a la cola
  (no tuvo ack) y la Saga continúa desde el último estado confirmado.
- Errores transitorios (timeout, bodega caída, 5xx) se propagan para que el consumidor reintente;
  al agotar los reintentos on_dead decide: compensar o dejar el caso para reconciliación.
"""
import logging
import time

from consumers import PermanentError
from db import Transfer, now, session_scope
from shared.observability import log
import warehouses
from warehouses import WarehouseError

logger = logging.getLogger("saga")
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}


class BusinessError(Exception):
    """Rechazo de negocio de una bodega (4xx): no se corrige reintentando."""


def call(wh, method, path, data=None, key=None):
    try:
        return warehouses.request(wh, method, path, data, headers={"Idempotency-Key": key} if key else None)[1]
    except WarehouseError as e:
        if 400 <= e.status < 500:
            raise BusinessError(f"{wh}: {e.body}") from None
        raise  # 5xx: transitorio


def movement(wh, product_id, type_, qty, transfer_id, step):
    return call(wh, "POST", "/inventory/movements",
                {"product_id": product_id, "type": type_, "quantity": qty, "reference": transfer_id},
                key=f"{transfer_id}:{step}")


def product_in(wh, sku):
    return call(wh, "GET", f"/products/by-sku/{sku}")


def ensure_product(t):
    """El destino puede no conocer el sku: se crea copiando los datos del origen."""
    try:
        return product_in(t.destination, t.sku)
    except BusinessError:
        src = product_in(t.source, t.sku)
        try:
            return call(t.destination, "POST", "/products", {k: src[k] for k in ("sku", "name", "description", "category", "unit")})
        except BusinessError:  # 409: otro paso lo creó en paralelo
            return product_in(t.destination, t.sku)


def set_status(transfer_id, status, detail=None, error=None):
    with session_scope() as db:
        t = db.get(Transfer, transfer_id)
        t.status, t.error = status, error
        t.history = [*(t.history or []), {"status": status, "at": now().isoformat(), "detail": detail}]
    log(logger, "transfer_status", transfer_id=transfer_id, status=status, detail=detail, error=error)


def load(transfer_id):
    with session_scope() as db:
        return db.get(Transfer, transfer_id)


def handle_transfer(msg: dict):
    tid = msg.get("transfer_id")
    t = load(tid) if tid else None
    if t is None:
        raise PermanentError(f"transferencia inexistente: {tid}")
    if t.status in TERMINAL:
        log(logger, "duplicate_command_ignored", transfer_id=tid, status=t.status)
        return
    while t.status not in TERMINAL:
        step(t)
        t = load(tid)
        if t.step_delay and t.status not in TERMINAL:
            time.sleep(min(t.step_delay, 10))


def step(t):
    s = t.status
    try:
        if s == "REQUESTED":
            if t.simulate_failure == "before_reserve":
                return set_status(t.id, "FAILED", error="fallo simulado antes de reservar (nada que compensar)")
            set_status(t.id, "RESERVING_SOURCE")
        elif s == "RESERVING_SOURCE":
            src = product_in(t.source, t.sku)
            movement(t.source, src["id"], "RESERVATION", t.quantity, t.id, "reserve")
            set_status(t.id, "SOURCE_RESERVED", f"{t.quantity} reservadas en {t.source}")
        elif s == "SOURCE_RESERVED":
            if t.simulate_failure == "after_reserve":
                return set_status(t.id, "COMPENSATING", error="fallo simulado después de reservar")
            set_status(t.id, "IN_TRANSIT")
        elif s == "IN_TRANSIT":
            dst = ensure_product(t)
            movement(t.destination, dst["id"], "TRANSFER_IN", t.quantity, t.id, "in")
            set_status(t.id, "DESTINATION_RECEIVED", f"{t.quantity} recibidas en {t.destination}")
        elif s == "DESTINATION_RECEIVED":
            src = product_in(t.source, t.sku)
            movement(t.source, src["id"], "TRANSFER_OUT", t.quantity, t.id, "out")
            set_status(t.id, "COMPLETED", f"reserva consumida en {t.source}")
        elif s == "COMPENSATING":
            src = product_in(t.source, t.sku)
            movement(t.source, src["id"], "RELEASE", t.quantity, t.id, "release")
            set_status(t.id, "CANCELLED", f"reserva liberada en {t.source}", error=t.error)
    except BusinessError as e:
        if s in ("REQUESTED", "RESERVING_SOURCE"):
            set_status(t.id, "FAILED", error=str(e))  # sin stock o sku inexistente: nada que deshacer
        elif s in ("SOURCE_RESERVED", "IN_TRANSIT"):
            set_status(t.id, "COMPENSATING", error=str(e))  # el destino rechazó: se deshace la reserva
        else:
            raise PermanentError(f"{s}: {e}")  # requiere reconciliación manual (ver on_dead)


def on_transfer_dead(msg: dict, error: str):
    """Reintentos agotados (bodega caída): decide si compensar."""
    t = load(msg.get("transfer_id"))
    if t is None or t.status in TERMINAL:
        return
    if t.status in ("SOURCE_RESERVED", "IN_TRANSIT"):
        # Destino inaccesible: se compensa. Riesgo aceptado: si el TRANSFER_IN se aplicó pero la
        # respuesta se perdió, la reconciliación lo detecta con GET /inventory/movements/by-key/TR-x:in.
        set_status(t.id, "COMPENSATING", error=f"destino no disponible: {error}")
        try:
            step(load(t.id))
        except Exception as e:
            set_status(t.id, "COMPENSATING", error=f"origen tampoco responde; reintentar con /transfers/{t.id}/redeliver ({e})")
    elif t.status in ("REQUESTED", "RESERVING_SOURCE"):
        set_status(t.id, "FAILED", error=f"origen no disponible: {error}. Verificar {t.id}:reserve en {t.source}")
    else:
        # DESTINATION_RECEIVED / COMPENSATING: las unidades ya se movieron o se están devolviendo;
        # no se compensa de nuevo, se reintenta más tarde.
        set_status(t.id, t.status, error=f"pendiente: {error}. Reintentar con /transfers/{t.id}/redeliver")
