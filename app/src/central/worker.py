"""Workers de la central (contenedor separado de la API): un hilo y una conexión por cola."""
import logging
import threading

from shared.observability import setup_logging

setup_logging()

from consumers import project_inventory_event, run_consumer  # noqa: E402
from db import Base, engine  # noqa: E402

CONSUMERS = {
    "central.projection": (project_inventory_event, None),
}

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    threads = [threading.Thread(target=run_consumer, args=(q, h, d), name=q, daemon=True) for q, (h, d) in CONSUMERS.items()]
    for t in threads:
        t.start()
    logging.getLogger("worker").info("central_worker_started")
    for t in threads:
        t.join()
