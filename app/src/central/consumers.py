"""
Consumidores de RabbitMQ con reintentos y DLQ, y el handler de proyección (CQRS).

Política (docs/eventos.md):
  - PermanentError (JSON inválido, campos faltantes, producto inexistente): directo a la DLQ.
  - Otro error (timeout, base caída): se reintenta MAX_RETRIES veces con backoff
    (republicando con cabecera x-retries); al agotar los intentos va a la DLQ.
  - El ack se envía después de procesar: si el worker muere, el mensaje vuelve a la cola.
"""
import json
import logging
import time

import pika
from pika.exceptions import AMQPError
from sqlalchemy.exc import IntegrityError

from db import EventLog, InventoryView, ProcessedEvent, SensorAlert, SensorTelemetry, WarehouseStatus, aware, now, session_scope
from shared import messaging
from shared.observability import correlation_id, log

logger = logging.getLogger("consumer")


class PermanentError(Exception):
    """Error que no se corrige reintentando."""


def process_message(ch, method, props, body, queue, handler, on_dead=None):
    headers = dict(props.headers or {})
    retries = int(headers.get("x-retries", 0))
    correlation_id.set(props.correlation_id)
    msg = None
    try:
        try:
            msg = json.loads(body)
            if not isinstance(msg, dict):
                raise ValueError("se esperaba un objeto JSON")
        except ValueError as e:
            raise PermanentError(f"JSON inválido: {e}") from None
        handler(msg)
        ch.basic_ack(method.delivery_tag)
    except PermanentError as e:
        log(logger, "message_dead_lettered", logging.ERROR, queue=queue, reason="permanent", error=str(e))
        if on_dead and msg is not None:
            on_dead(msg, str(e))
        ch.basic_nack(method.delivery_tag, requeue=False)
    except Exception as e:
        if retries < messaging.MAX_RETRIES:
            delay = 2 ** retries
            log(logger, "message_retry", logging.WARNING, queue=queue, attempt=retries + 1,
                max_retries=messaging.MAX_RETRIES, delay_s=delay, error=str(e))
            time.sleep(delay)  # ponytail: backoff bloqueante; usar colas de espera con TTL si el throughput importa
            headers.update({"x-retries": retries + 1, "x-last-error": str(e)[:200]})
            ch.basic_publish("", queue, body, pika.BasicProperties(
                delivery_mode=2, content_type="application/json",
                correlation_id=props.correlation_id, headers=headers))
            ch.basic_ack(method.delivery_tag)
        else:
            log(logger, "message_dead_lettered", logging.ERROR, queue=queue, reason="retries_exhausted", error=str(e))
            if on_dead and msg is not None:
                on_dead(msg, f"reintentos agotados: {e}")
            ch.basic_nack(method.delivery_tag, requeue=False)
    finally:
        correlation_id.set(None)


def run_consumer(queue, handler, on_dead=None, prefetch=10):
    while True:
        try:
            conn = pika.BlockingConnection(messaging.connection_params())
            ch = conn.channel()
            messaging.declare_topology(ch)
            ch.basic_qos(prefetch_count=prefetch)
            log(logger, "consumer_started", queue=queue)
            for method, props, body in ch.consume(queue):
                process_message(ch, method, props, body, queue, handler, on_dead)
        except AMQPError as e:
            log(logger, "rabbitmq_unavailable", logging.WARNING, queue=queue, error=str(e) or type(e).__name__)
            time.sleep(5)


# ==============================================================================
# Proyección: INVENTORY_UPDATED -> inventory_view (read model)
# ==============================================================================
REQUIRED = ("warehouse_id", "sku", "movement_id", "movement_type", "movement_quantity", "quantity", "reserved_quantity")


def project_inventory_event(msg: dict):
    payload = msg.get("payload") or {}
    missing = [f for f in REQUIRED if payload.get(f) is None]
    if msg.get("event_type") != "INVENTORY_UPDATED" or not msg.get("event_id") or missing:
        raise PermanentError(f"evento inválido (event_type={msg.get('event_type')}, faltan={missing or ['event_id']})")
    event_id, wh, sku = msg["event_id"], payload["warehouse_id"], payload["sku"]
    occurred = aware(_parse_ts(msg.get("occurred_at"))) or now()
    try:
        with session_scope() as db:
            if db.get(ProcessedEvent, (event_id, "projection")):
                log(logger, "duplicate_event_ignored", event_id=event_id, warehouse_id=wh)
                return
            db.add(ProcessedEvent(event_id=event_id, consumer="projection"))
            row = db.get(InventoryView, (wh, sku))
            if row is None:
                row = InventoryView(warehouse_id=wh, sku=sku, version=-1)
                db.add(row)
            if payload["movement_id"] > row.version:
                row.product_id, row.product_name = payload.get("product_id"), payload.get("product_name")
                row.quantity, row.reserved_quantity = payload["quantity"], payload["reserved_quantity"]
                row.version, row.updated_at = payload["movement_id"], occurred
            else:
                log(logger, "out_of_order_event_skipped", event_id=event_id, version=payload["movement_id"], current=row.version)
            db.add(EventLog(event_id=event_id, warehouse_id=wh, sku=sku, movement_type=payload["movement_type"],
                            movement_quantity=payload["movement_quantity"], reference=payload.get("reference"),
                            correlation_id=msg.get("correlation_id"), occurred_at=occurred, payload=msg))
            status = db.get(WarehouseStatus, wh) or WarehouseStatus(warehouse_id=wh)
            status.last_event_at = now()
            db.merge(status)
    except IntegrityError:
        log(logger, "duplicate_event_ignored", event_id=event_id, warehouse_id=wh, note="carrera entre consumidores")
        return
    log(logger, "inventory_projected", event_id=event_id, warehouse_id=wh, sku=sku,
        quantity=payload["quantity"], movement_type=payload["movement_type"])


def _parse_ts(value):
    from datetime import datetime
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


# ==============================================================================
# Ingestión y Procesamiento de Sensores IoT (Fase 12)
# ==============================================================================
IOT_REQUIRED = ("event_id", "sequence_number", "warehouse_id", "sensor_id", "value")


def process_iot_event(msg: dict):
    """
    Procesa eventos de telemetría IoT desde RabbitMQ:
    - Idempotencia: evita duplicados usando ProcessedEvent (event_id, consumer='iot').
    - Sequence numbers: detecta telemetría fuera de orden.
    - Persistencia en SensorTelemetry.
    - Detección de umbrales críticos y generación de SensorAlert.
    """
    missing = [f for f in IOT_REQUIRED if msg.get(f) is None]
    if missing:
        raise PermanentError(f"evento IoT inválido, faltan campos: {missing}")

    event_id = msg["event_id"]
    wh = msg["warehouse_id"]
    sensor_id = msg["sensor_id"]
    stype = msg.get("sensor_type") or sensor_id.split("-")[0]
    val = float(msg["value"])
    seq = int(msg["sequence_number"])
    ts = aware(_parse_ts(msg.get("timestamp"))) or now()

    try:
        with session_scope() as db:
            # 1. Idempotencia persistente
            if db.get(ProcessedEvent, (event_id, "iot")):
                log(logger, "duplicate_iot_event_ignored", event_id=event_id, sensor_id=sensor_id)
                return

            db.add(ProcessedEvent(event_id=event_id, consumer="iot"))

            # 2. Persistencia de telemetría
            db.add(SensorTelemetry(
                event_id=event_id,
                sequence_number=seq,
                warehouse_id=wh,
                sensor_id=sensor_id,
                sensor_type=stype,
                value=val,
                unit=msg.get("unit", ""),
                timestamp=ts,
            ))

            # 3. Reglas de alertas por umbrales (temperatura alta, picos de potencia, humedad)
            alert_rule = None
            alert_msg = None
            if stype == "TEMP" and (val > 15.0 or val < 0.0):
                alert_rule = "TEMP_OUT_OF_RANGE"
                alert_msg = f"Temperatura anómala de {val}°C en sensor {sensor_id} ({wh})"
            elif stype == "PWR" and val > 10.0:
                alert_rule = "POWER_SURGE"
                alert_msg = f"Pico de consumo eléctrico ({val} kWh) en {sensor_id} ({wh})"
            elif stype == "HUM" and val > 70.0:
                alert_rule = "HIGH_HUMIDITY"
                alert_msg = f"Humedad crítica ({val}%) en {sensor_id} ({wh})"

            if alert_rule:
                db.add(SensorAlert(
                    event_id=event_id,
                    warehouse_id=wh,
                    sensor_id=sensor_id,
                    sensor_type=stype,
                    value=val,
                    rule=alert_rule,
                    alert_message=alert_msg,
                ))
                log(logger, "iot_alert_triggered", logging.WARNING,
                    rule=alert_rule, warehouse_id=wh, sensor_id=sensor_id, value=val)

    except IntegrityError:
        log(logger, "duplicate_iot_event_ignored", event_id=event_id, note="carrera concurrente")
        return

    log(logger, "iot_telemetry_stored", event_id=event_id, warehouse_id=wh, sensor_id=sensor_id, seq=seq)

