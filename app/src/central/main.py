import os
import time
import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Central: %(message)s")
logger = logging.getLogger("CentralPlatform")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "warehouse_events")

# ==============================================================================
# Almacén de Métricas y Eventos Consolidados (CQRS Read Model)
# ==============================================================================
lock = threading.Lock()
processed_event_ids = set() # Idempotencia: evita procesar dos veces el mismo evento
events_history: List[Dict[str, Any]] = []

summary_by_warehouse: Dict[str, Dict[str, Any]] = {
    "WH-001": {"total_events": 0, "by_type": {}, "last_event_at": None},
    "WH-002": {"total_events": 0, "by_type": {}, "last_event_at": None},
    "WH-003": {"total_events": 0, "by_type": {}, "last_event_at": None},
}

def record_event(data: Dict[str, Any]):
    event_id = data.get("event_id")
    warehouse_id = data.get("warehouse_id", "UNKNOWN").upper().replace("_", "-")
    event_type = data.get("event_type", "UNKNOWN")
    timestamp = data.get("timestamp", datetime.utcnow().isoformat())

    with lock:
        # Control de Idempotencia (Fase 10)
        if event_id and event_id in processed_event_ids:
            logger.info(f"🔁 [Idempotencia] Evento {event_id} ya fue procesado. Descartando duplicado.")
            return

        if event_id:
            processed_event_ids.add(event_id)

        # Inicializar bodega si no existía en el mapa
        if warehouse_id not in summary_by_warehouse:
            summary_by_warehouse[warehouse_id] = {"total_events": 0, "by_type": {}, "last_event_at": None}

        # Actualizar métricas
        wh_summary = summary_by_warehouse[warehouse_id]
        wh_summary["total_events"] += 1
        wh_summary["last_event_at"] = timestamp
        wh_summary["by_type"][event_type] = wh_summary["by_type"].get(event_type, 0) + 1

        events_history.append({
            "received_at": datetime.utcnow().isoformat(),
            **data
        })

    logger.info(f"📊 [Evento Registrado] Sucursal: {warehouse_id} | Tipo: {event_type} | Total Sucursal: {wh_summary['total_events']}")

# ==============================================================================
# Consumidor de RabbitMQ en Segundo Plano
# ==============================================================================
def rabbitmq_consumer():
    logger.info("🚀 Iniciando Consumidor Central de RabbitMQ...")

    while True:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                connection_attempts=1,
                retry_delay=1,
                socket_timeout=5
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=10)

            def on_message(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode("utf-8"))
                    record_event(payload)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as parse_err:
                    logger.error(f"❌ Error al procesar mensaje: {parse_err}")
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=on_message)
            logger.info(f"🟢 [Consumidor Central] Conectado a RabbitMQ. Escuchando cola '{RABBITMQ_QUEUE}'...")
            channel.start_consuming()

        except (AMQPConnectionError, AMQPChannelError, Exception) as e:
            logger.warning(f"⚠️ [Consumidor Central] RabbitMQ no disponible ({e}). Reintentando en 5s...")
            time.sleep(5)

# ==============================================================================
# API REST de la Plataforma Central y Reportes
# ==============================================================================
app = FastAPI(
    title="Warehouse Cloud Platform — Plataforma Central y Reportería",
    description="Consolidación de eventos CQRS y sistema de reportes por sucursal.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=rabbitmq_consumer, daemon=True, name="CentralConsumerThread")
    thread.start()

@app.get("/health")
def health():
    return {"status": "online", "service": "central-reporting-platform"}

@app.get("/reports/events-by-warehouse")
def get_events_by_warehouse_report():
    """
    REQUERIMIENTO: Sistema de reportes: cuántos eventos llegan por sucursal.
    Retorna el resumen consolidado de eventos recibidos por cada bodega.
    """
    with lock:
        total_global = sum(wh["total_events"] for wh in summary_by_warehouse.values())
        return {
            "report_title": "Consolidado de Eventos Recibidos por Sucursal",
            "generated_at": datetime.utcnow().isoformat(),
            "total_events_received": total_global,
            "warehouses_summary": summary_by_warehouse
        }

@app.get("/reports/events")
def get_all_events(limit: int = 100):
    """Retorna el registro detallado de los últimos eventos recibidos de las bodegas."""
    with lock:
        return {
            "total_records": len(events_history),
            "events": list(reversed(events_history[-limit:]))
        }

@app.post("/reports/reset")
def reset_metrics():
    """Reinicia los contadores para demostraciones en vivo."""
    with lock:
        processed_event_ids.clear()
        events_history.clear()
        for wh in summary_by_warehouse:
            summary_by_warehouse[wh] = {"total_events": 0, "by_type": {}, "last_event_at": None}
    return {"status": "ok", "message": "Métricas de eventos reiniciadas"}
