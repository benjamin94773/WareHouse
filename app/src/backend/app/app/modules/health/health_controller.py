from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cache
from app.config import settings
from app.database import get_db
from shared.observability import INSTANCE, metrics

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check(response: Response, db: Session = Depends(get_db)):
    """Lo usa el load balancer: si la base no responde, la réplica deja de recibir tráfico."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "warehouse_id": settings.WAREHOUSE_ID, "instance": INSTANCE}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "detail": str(e), "instance": INSTANCE}


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """Métricas de esta réplica + Redis + PostgreSQL (compartidos por todas las réplicas)."""
    result = {"warehouse_id": settings.WAREHOUSE_ID, "api": metrics.snapshot(), "redis": None, "postgres": None}
    try:
        info = cache._client.info()
        hits, misses = info["keyspace_hits"], info["keyspace_misses"]
        result["redis"] = {
            "enabled": settings.CACHE_ENABLED,
            "hits": hits,
            "misses": misses,
            "hit_ratio": round(hits / (hits + misses), 4) if hits + misses else None,
            "used_memory_human": info["used_memory_human"],
        }
    except Exception as e:
        result["redis"] = {"enabled": settings.CACHE_ENABLED, "error": str(e)}
    if db.bind.dialect.name == "postgresql":
        row = db.execute(text("""
            SELECT (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections,
                   (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active') AS active,
                   (SELECT count(*) FROM pg_locks WHERE NOT granted) AS waiting_locks,
                   (SELECT count(*) FROM outbox_events WHERE status = 'PENDING') AS outbox_pending
        """)).mappings().one()
        result["postgres"] = dict(row)
    return result
