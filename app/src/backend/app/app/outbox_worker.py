import time
import json
import logging
import threading
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError
from app.config import settings
from app.database import SessionLocal
from app.modules.inventory.inventory_repository import InventoryRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("OutboxWorker")

class OutboxWorker:
    """
    Worker resiliente del Patrón Transactional Outbox.
    Monitorea la tabla local 'outbox_events' y transmite los eventos pendientes hacia RabbitMQ.
    Si RabbitMQ está caído, maneja el fallo sin detener la aplicación y reintenta automáticamente
    al restablecerse el servicio, garantizando 'At-Least-Once Delivery' sin pérdida de eventos.
    """

    def __init__(self):
        self.running = True
        self.connection = None
        self.channel = None

    def connect_broker(self) -> bool:
        """Intenta establecer conexión con RabbitMQ. Retorna True si tiene éxito, False si está caído."""
        try:
            credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials,
                connection_attempts=1,
                retry_delay=1,
                socket_timeout=3
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            # Declarar cola durable para que los mensajes sobrevivan reinicios del broker
            self.channel.queue_declare(queue=settings.RABBITMQ_QUEUE, durable=True)
            return True
        except (AMQPConnectionError, Exception) as e:
            self.connection = None
            self.channel = None
            return False

    def publish_pending_events(self):
        """Lee los eventos pendientes de la base de datos local y los publica al broker."""
        db = SessionLocal()
        try:
            repo = InventoryRepository(db)
            pending_events = repo.get_pending_outbox_events(limit=50)

            if not pending_events:
                return

            logger.info(f"📤 [Outbox] Procesando {len(pending_events)} evento(s) pendiente(s)...")

            for event in pending_events:
                try:
                    self.channel.basic_publish(
                        exchange="",
                        routing_key=settings.RABBITMQ_QUEUE,
                        body=event.payload.encode("utf-8"),
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Mensaje persistente en disco en RabbitMQ
                            content_type="application/json",
                            headers={"warehouse_id": event.warehouse_id, "event_type": event.event_type}
                        )
                    )
                    repo.mark_outbox_event_sent(event.id)
                    logger.info(f"✅ [Outbox] Evento {event.id} ({event.event_type}) entregado a RabbitMQ.")
                except Exception as pub_err:
                    logger.warning(f"⚠️ [Outbox] Error enviando evento {event.id}: {pub_err}")
                    repo.increment_outbox_retry(event.id)
                    raise pub_err

        finally:
            db.close()

    def run_loop(self):
        """Bucle continuo de sondeo y reintentos."""
        logger.info(f"🚀 Outbox Worker iniciado para bodega: {settings.WAREHOUSE_ID}")
        
        while self.running:
            try:
                # 1. Verificar o restaurar conexión con RabbitMQ
                if not self.connection or self.connection.is_closed:
                    logger.info("🔄 Intentando conectar con RabbitMQ broker...")
                    connected = self.connect_broker()
                    if not connected:
                        logger.warning("❌ [Outbox] RabbitMQ no disponible (caído o inalcanzable). Reintentando en 5s...")
                        logger.info("🛡️ [Outbox] Los eventos permanecen seguros y resguardados en PostgreSQL.")
                        time.sleep(5)
                        continue
                    else:
                        logger.info("🟢 [Outbox] Conexión establecida exitosamente con RabbitMQ.")

                # 2. Publicar eventos pendientes
                self.publish_pending_events()
                time.sleep(2)

            except (AMQPConnectionError, AMQPChannelError, Exception) as e:
                logger.warning(f"⚠️ [Outbox] Conexión con RabbitMQ interrumpida: {e}. Reintentando...")
                try:
                    if self.connection and not self.connection.is_closed:
                        self.connection.close()
                except Exception:
                    pass
                self.connection = None
                self.channel = None
                time.sleep(5)

    def start_background(self):
        """Inicia el worker en un hilo en segundo plano no bloqueante."""
        thread = threading.Thread(target=self.run_loop, daemon=True, name="OutboxWorkerThread")
        thread.start()
        return thread

outbox_worker = OutboxWorker()
