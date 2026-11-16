"""
Outbox relay: publica en RabbitMQ los eventos PENDING de outbox_events.

Corre como contenedor propio (python -m app.outbox_relay), separado de las réplicas
de la API. Garantía at-least-once:
  - publisher confirms + mandatory: solo se marca SENT si el broker lo aceptó y lo
    enrutó a alguna cola; si no hay cola (central aún sin desplegar) queda PENDING;
  - si el proceso cae entre publicar y marcar SENT, el evento se reenvía y el
    consumidor lo descarta por event_id (idempotencia).
Con RabbitMQ caído la API sigue aceptando movimientos: los eventos esperan en PostgreSQL.
"""
import json
import logging
import time

import pika
from pika.exceptions import AMQPError, UnroutableError

from app.config import settings
from app.database import SessionLocal
from app.modules.inventory.models import OutboxEventEntity
from app.modules.shared.utils.schemas_utils import current_utc_time
from shared import messaging
from shared.observability import correlation_id, log, setup_logging

logger = logging.getLogger("outbox_relay")
BATCH = 100


def connect():
    conn = pika.BlockingConnection(messaging.connection_params())
    ch = conn.channel()
    messaging.declare_exchanges(ch)
    ch.confirm_delivery()
    return conn, ch


def publish_batch(ch) -> int:
    db = SessionLocal()
    sent = 0
    try:
        events = (db.query(OutboxEventEntity)
                  .filter(OutboxEventEntity.status == "PENDING")
                  .order_by(OutboxEventEntity.created_at)
                  .with_for_update(skip_locked=True)  # seguro aunque se escalen varios relays
                  .limit(BATCH).all())
        for ev in events:
            body = json.loads(ev.payload)
            correlation_id.set(body.get("correlation_id"))
            try:
                ch.basic_publish(
                    exchange=messaging.EVENTS_EXCHANGE,
                    routing_key=f"inventory.updated.{ev.warehouse_id}",
                    body=ev.payload.encode(),
                    properties=messaging.persistent(body.get("correlation_id"), {"event_type": ev.event_type}),
                    mandatory=True,
                )
            except UnroutableError:
                ev.retry_count += 1
                log(logger, "outbox_unroutable", logging.WARNING, event_id=ev.id,
                    hint="no hay cola enlazada; ¿está desplegada la central?")
                break
            ev.status, ev.sent_at = "SENT", current_utc_time()
            sent += 1
            log(logger, "outbox_event_published", event_id=ev.id, event_type=ev.event_type)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        correlation_id.set(None)
    return sent


def run():
    setup_logging()
    log(logger, "outbox_relay_started", warehouse_id=settings.WAREHOUSE_ID)
    conn = ch = None
    while True:
        try:
            if conn is None or conn.is_closed:
                conn, ch = connect()
                log(logger, "rabbitmq_connected")
            if publish_batch(ch) < BATCH:
                time.sleep(1)
        except AMQPError as e:
            log(logger, "rabbitmq_unavailable", logging.WARNING, error=str(e) or type(e).__name__,
                note="eventos resguardados en PostgreSQL; reintento en 5 s")
            conn = None
            time.sleep(5)
        except Exception as e:  # p. ej. PostgreSQL caído
            log(logger, "outbox_relay_error", logging.ERROR, error=str(e))
            time.sleep(5)


if __name__ == "__main__":
    run()
