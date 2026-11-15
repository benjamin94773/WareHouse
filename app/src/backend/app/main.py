from fastapi import FastAPI
from app.database import engine, Base
from app.modules.health.health_controller import router as health_controller
from app.modules.products.products_controller import router as products_controller
from app.modules.inventory.inventory_controller import router as inventory_controller
from app.outbox_worker import outbox_worker

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Warehouse Cloud Platform — Bodega Node",
    description="Nodo de Bodega Autónoma con Patrón Transactional Outbox y resiliencia ante caídas del broker.",
    version="1.2.0"
)

app.include_router(health_controller)
app.include_router(products_controller)
app.include_router(inventory_controller)

@app.on_event("startup")
def startup_event():
    # Inicia el Outbox Worker en segundo plano para sincronizar eventos con RabbitMQ
    outbox_worker.start_background()
