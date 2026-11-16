import glob
import os

from fastapi import FastAPI
from sqlalchemy import text

from shared.observability import install, setup_logging

setup_logging()

from app.database import Base, engine  # noqa: E402
from app.modules.health.health_controller import router as health_controller  # noqa: E402
from app.modules.inventory.inventory_controller import router as inventory_controller  # noqa: E402
from app.modules.products.products_controller import router as products_controller  # noqa: E402

Base.metadata.create_all(bind=engine)


def run_migrations():
    """Aplica db/migrations/*.sql en orden; cada script es idempotente (IF NOT EXISTS)."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(42)"))  # las réplicas arrancan a la vez
        for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "db", "migrations", "*.sql"))):
            conn.exec_driver_sql(open(path).read())


run_migrations()

app = FastAPI(
    title="Warehouse Cloud Platform — Bodega",
    description="API autónoma de bodega: productos, inventario, Cache Aside y Transactional Outbox.",
    version="2.0.0",
)
install(app)

app.include_router(health_controller)
app.include_router(products_controller)
app.include_router(inventory_controller)

