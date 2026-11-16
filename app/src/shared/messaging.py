"""
Topología de RabbitMQ compartida (ver docs/eventos.md).

  warehouse.events (topic) --inventory.#-->  central.projection  --DLX--> central.projection.dlq
  central.commands (direct) --transfer-->    central.transfers   --DLX--> central.transfers.dlq
                            --report-->      central.reports     --DLX--> central.reports.dlq
"""
import os

import pika

EVENTS_EXCHANGE = "warehouse.events"
COMMANDS_EXCHANGE = "central.commands"
DLX = "warehouse.dlx"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# cola -> (exchange, routing key de binding)
QUEUES = {
    "central.projection": (EVENTS_EXCHANGE, "inventory.#"),
    "central.transfers": (COMMANDS_EXCHANGE, "transfer"),
    "central.reports": (COMMANDS_EXCHANGE, "report"),
}


def connection_params(timeout=5) -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        credentials=pika.PlainCredentials(os.getenv("RABBITMQ_USER", "guest"), os.getenv("RABBITMQ_PASS", "guest")),
        connection_attempts=1,
        socket_timeout=timeout,
        heartbeat=30,
    )


def declare_exchanges(ch):
    ch.exchange_declare(EVENTS_EXCHANGE, "topic", durable=True)
    ch.exchange_declare(COMMANDS_EXCHANGE, "direct", durable=True)
    ch.exchange_declare(DLX, "direct", durable=True)


def declare_topology(ch):
    """Colas durables con dead-letter: un nack sin requeue envía el mensaje a <cola>.dlq."""
    declare_exchanges(ch)
    for queue, (exchange, key) in QUEUES.items():
        ch.queue_declare(f"{queue}.dlq", durable=True)
        ch.queue_bind(f"{queue}.dlq", DLX, routing_key=queue)
        ch.queue_declare(queue, durable=True, arguments={
            "x-dead-letter-exchange": DLX,
            "x-dead-letter-routing-key": queue,
        })
        ch.queue_bind(queue, exchange, routing_key=key)


def persistent(correlation_id=None, headers=None) -> pika.BasicProperties:
    return pika.BasicProperties(
        delivery_mode=2,  # el mensaje sobrevive a un reinicio del broker
        content_type="application/json",
        correlation_id=correlation_id,
        headers=headers or {},
    )
