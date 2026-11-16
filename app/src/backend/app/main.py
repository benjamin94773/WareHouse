from fastapi import FastAPI

from shared.observability import install, setup_logging

setup_logging()

from app.database import Base, engine  # noqa: E402
from app.modules.health.health_controller import router as health_controller  # noqa: E402
from app.modules.inventory.inventory_controller import router as inventory_controller  # noqa: E402
from app.modules.products.products_controller import router as products_controller  # noqa: E402

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Warehouse Cloud Platform — Bodega",
    description="API autónoma de bodega: productos, inventario, Cache Aside y Transactional Outbox.",
    version="2.0.0",
)
install(app)

app.include_router(health_controller)
app.include_router(products_controller)
app.include_router(inventory_controller)

