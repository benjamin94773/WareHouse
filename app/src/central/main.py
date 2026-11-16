"""API de la plataforma central: consultas globales (read model), estado de bodegas y administración."""
import json
import logging
import os
import threading
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, Literal, Optional

import pika
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.observability import correlation_id, install, log, metrics, setup_logging

setup_logging()

import reports  # noqa: E402
import warehouses  # noqa: E402
from db import Base, EventLog, IntegrationEvent, InventoryView, ProcessedEvent, ReportJob, Transfer, WarehouseStatus, aware, engine, get_db, now, session_scope  # noqa: E402
from shared import messaging  # noqa: E402

logger = logging.getLogger("central_api")
STALE_AFTER = timedelta(seconds=int(os.getenv("STALE_AFTER_SECONDS", "30")))
INDEX_HTML_PATH = os.path.join(os.path.dirname(__file__), "index.html")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Warehouse Cloud Platform — Central",
    description="Read model global (CQRS), sagas de transferencia, reportes y estado de bodegas.",
    version="2.0.0",
)
install(app)


# ==============================================================================
# Health poller: detecta bodegas inaccesibles para marcar su información como desactualizada
# ==============================================================================
def poll_warehouses():
    while True:
        for wh in warehouses.warehouse_urls():
            try:
                warehouses.request(wh, "GET", "/health", timeout=2)
                ok, error = True, None
            except Exception as e:
                ok, error = False, str(e)[:300]
            try:
                with session_scope() as db:
                    st = db.get(WarehouseStatus, wh) or WarehouseStatus(warehouse_id=wh)
                    if ok:
                        st.last_health_ok_at = now()
                    elif st.healthy:
                        log(logger, "warehouse_unreachable", logging.WARNING, warehouse_id=wh, error=error)
                    st.healthy, st.last_error = ok, error
                    db.merge(st)
            except Exception as e:
                log(logger, "health_poll_error", logging.ERROR, error=str(e))
        time.sleep(10)


@app.on_event("startup")
def startup():
    threading.Thread(target=poll_warehouses, daemon=True, name="warehouse-health").start()


def warehouse_freshness(db: Session) -> Dict[str, dict]:
    statuses = {s.warehouse_id: s for s in db.query(WarehouseStatus).all()}
    result = {}
    for wh in sorted(set(warehouses.warehouse_urls()) | set(statuses)):
        st = statuses.get(wh)
        last_ok = aware(st.last_health_ok_at) if st else None
        stale = not (st and st.healthy and last_ok and now() - last_ok < STALE_AFTER)
        result[wh] = {
            "reachable": bool(st and st.healthy),
            "stale": stale,
            "last_health_ok_at": last_ok,
            "last_event_at": aware(st.last_event_at) if st else None,
            "last_error": st.last_error if st else "sin chequeos todavía",
        }
    return result


# ==============================================================================
# Consultas globales (Query side de CQRS)
# ==============================================================================
@app.get("/health")
def health():
    return {"status": "ok", "service": "central-api"}


@app.get("/metrics")
def central_metrics(db: Session = Depends(get_db)):
    """API central + RabbitMQ (profundidad, DLQ) + workers (procesados y tasa, derivados de la base)."""
    minute_ago = now() - timedelta(minutes=1)
    try:
        queues = queue_depths()
    except Exception as e:
        queues = {"error": f"RabbitMQ no disponible: {e}"}
    return {
        "api": metrics.snapshot(),
        "rabbitmq": queues,
        "workers": {
            "projection": {
                "processed_total": db.query(func.count(ProcessedEvent.event_id)).scalar(),
                "processed_last_minute": db.query(func.count(ProcessedEvent.event_id)).filter(ProcessedEvent.processed_at >= minute_ago).scalar(),
            },
            "transfers_by_status": dict(db.query(Transfer.status, func.count()).group_by(Transfer.status).all()),
            "report_jobs_by_status": dict(db.query(ReportJob.status, func.count()).group_by(ReportJob.status).all()),
        },
        "warehouses": warehouse_freshness(db),
    }


@app.get("/warehouses/status")
def warehouses_status(db: Session = Depends(get_db)):
    return warehouse_freshness(db)


@app.get("/global/inventory")
def global_inventory(db: Session = Depends(get_db)):
    rows = (db.query(InventoryView.sku, func.max(InventoryView.product_name),
                     func.sum(InventoryView.quantity), func.sum(InventoryView.reserved_quantity))
            .group_by(InventoryView.sku).order_by(InventoryView.sku).all())
    return [{"sku": s, "name": n, "total_quantity": q, "total_reserved": r} for s, n, q, r in rows]


@app.get("/global/inventory/{sku}")
def global_inventory_by_sku(sku: str, db: Session = Depends(get_db)):
    """Alternativa B (read model): una sola consulta local, sin depender de que las bodegas respondan."""
    rows = db.query(InventoryView).filter(InventoryView.sku == sku).all()
    if not rows:
        raise HTTPException(404, f"Sin datos para el sku {sku} en el read model")
    fresh = warehouse_freshness(db)
    detail, warnings = [], []
    for r in sorted(rows, key=lambda r: r.warehouse_id):
        f = fresh.get(r.warehouse_id, {"stale": True, "reachable": False})
        detail.append({"warehouse_id": r.warehouse_id, "quantity": r.quantity, "reserved_quantity": r.reserved_quantity,
                       "last_updated_at": aware(r.updated_at), "stale": f["stale"], "reachable": f["reachable"]})
        if f["stale"]:
            warnings.append(f"{r.warehouse_id}: bodega inaccesible; su información puede estar desactualizada")
    for wh in sorted(set(fresh) - {r.warehouse_id for r in rows}):
        warnings.append(f"{wh}: sin eventos para este sku en el read model")
    return {
        "sku": sku,
        "name": rows[0].product_name,
        "total_quantity": sum(r.quantity for r in rows),
        "total_reserved": sum(r.reserved_quantity for r in rows),
        "consistency": "eventual",
        "strategy": "read model (CQRS)",
        "warehouses": detail,
        "warnings": warnings,
    }


@app.get("/global/inventory/{sku}/live")
def global_inventory_live(sku: str):
    """Alternativa A, solo para comparar latencia y disponibilidad con el read model."""
    return warehouses.live_inventory(sku)


# ==============================================================================
# Transferencias (Saga orquestada por el worker)
# ==============================================================================
class TransferRequest(BaseModel):
    source: str
    destination: str
    sku: str
    quantity: int = Field(..., gt=0)
    simulate_failure: Optional[Literal["before_reserve", "after_reserve"]] = None
    step_delay: int = Field(0, ge=0, le=10)


def publish_command(routing_key: str, body: dict):
    conn, ch = _channel()
    try:
        ch.confirm_delivery()
        ch.basic_publish(messaging.COMMANDS_EXCHANGE, routing_key, json.dumps(body).encode(),
                         messaging.persistent(correlation_id.get()), mandatory=True)
    finally:
        conn.close()


def transfer_view(t: Transfer):
    return {c.name: getattr(t, c.name) for c in Transfer.__table__.columns}


@app.post("/transfers", status_code=202)
def create_transfer(req: TransferRequest, db: Session = Depends(get_db)):
    src, dst = req.source.upper(), req.destination.upper()
    known = warehouses.warehouse_urls()
    if src == dst or src not in known or dst not in known:
        raise HTTPException(422, f"Origen y destino deben ser bodegas distintas de {sorted(known)}")
    t = Transfer(id=f"TR-{uuid.uuid4().hex[:8].upper()}", source=src, destination=dst, sku=req.sku,
                 quantity=req.quantity, status="REQUESTED", simulate_failure=req.simulate_failure,
                 step_delay=req.step_delay, correlation_id=correlation_id.get(),
                 history=[{"status": "REQUESTED", "at": now().isoformat()}])
    db.add(t)
    db.commit()
    try:
        publish_command("transfer", {"transfer_id": t.id})
    except Exception as e:
        # Operación crítica sin broker: se rechaza en vez de dejarla a medias (ver ADR de RabbitMQ caído)
        t.status, t.error = "FAILED", f"broker no disponible: {e}"
        db.commit()
        raise HTTPException(503, f"RabbitMQ no disponible; transferencia {t.id} rechazada")
    return {"transfer_id": t.id, "status": "PROCESSING", "correlation_id": t.correlation_id}


@app.get("/transfers")
def list_transfers(limit: int = 20, db: Session = Depends(get_db)):
    return [transfer_view(t) for t in db.query(Transfer).order_by(Transfer.created_at.desc()).limit(limit)]


@app.get("/transfers/{transfer_id}")
def get_transfer(transfer_id: str, db: Session = Depends(get_db)):
    t = db.get(Transfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transferencia no encontrada")
    return transfer_view(t)


@app.post("/transfers/{transfer_id}/redeliver")
def redeliver_transfer(transfer_id: str, db: Session = Depends(get_db)):
    """Reenvía el comando: retoma una Saga pendiente o, si ya terminó, prueba que el duplicado se ignora."""
    if not db.get(Transfer, transfer_id):
        raise HTTPException(404, "Transferencia no encontrada")
    publish_command("transfer", {"transfer_id": transfer_id})
    return {"transfer_id": transfer_id, "redelivered": True}


# ==============================================================================
# Reportes asíncronos (Fase 3) generados por el batch hacia S3 (Fase 8)
# ==============================================================================
class ReportRequest(BaseModel):
    type: Literal["daily"] = "daily"
    date: Optional[str] = Field(None, description="AAAA-MM-DD; por defecto hoy (UTC)")


@app.post("/reports", status_code=202)
def request_report(req: ReportRequest):
    try:
        job_id = reports.create_job(req.date or now().date().isoformat(), trigger="api")
    except ValueError:
        raise HTTPException(422, "date debe tener formato AAAA-MM-DD")
    try:
        publish_command("report", {"job_id": job_id})
    except Exception as e:
        reports.on_report_dead({"job_id": job_id}, f"broker no disponible: {e}")
        raise HTTPException(503, f"RabbitMQ no disponible; job {job_id} rechazado")
    return {"job_id": job_id, "status": "PROCESSING"}


@app.get("/reports/jobs")
def list_jobs(limit: int = 20, db: Session = Depends(get_db)):
    return db.query(ReportJob).order_by(ReportJob.created_at.desc()).limit(limit).all()


@app.get("/reports/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ReportJob, job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job


@app.post("/integrations/lambda-events", status_code=201)
def lambda_event(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """La Lambda de S3 publica aquí el resultado de validar cada reporte."""
    db.add(IntegrationEvent(source="lambda:report-validator", payload=payload))
    db.commit()
    log(logger, "lambda_event_received", key=payload.get("key"), valid=payload.get("valid"))
    return {"received": True}


@app.get("/integrations/lambda-events")
def list_lambda_events(limit: int = 20, db: Session = Depends(get_db)):
    return db.query(IntegrationEvent).order_by(IntegrationEvent.id.desc()).limit(limit).all()


# ==============================================================================
# Administración de RabbitMQ: profundidad de colas, DLQ y experimentos de fallos
# ==============================================================================
def _channel():
    conn = pika.BlockingConnection(messaging.connection_params())
    ch = conn.channel()
    messaging.declare_topology(ch)
    return conn, ch


@app.get("/admin/queues")
def queue_depths():
    conn, ch = _channel()
    try:
        out = {}
        for q in messaging.QUEUES:
            for name in (q, f"{q}.dlq"):
                d = ch.queue_declare(name, passive=True)
                out[name] = {"messages": d.method.message_count, "consumers": d.method.consumer_count}
        return out
    finally:
        conn.close()


@app.post("/admin/dlq/{queue}/replay")
def replay_dlq(queue: str):
    """Recuperación: reinyecta los mensajes de <queue>.dlq en <queue> con el contador de reintentos en cero."""
    if queue not in messaging.QUEUES:
        raise HTTPException(404, f"Cola desconocida. Opciones: {list(messaging.QUEUES)}")
    conn, ch = _channel()
    moved = 0
    try:
        while True:
            method, props, body = ch.basic_get(f"{queue}.dlq")
            if method is None:
                break
            headers = {k: v for k, v in (props.headers or {}).items() if k not in ("x-retries", "x-death")}
            ch.basic_publish("", queue, body, messaging.persistent(props.correlation_id, headers))
            ch.basic_ack(method.delivery_tag)
            moved += 1
    finally:
        conn.close()
    return {"queue": queue, "replayed": moved}


@app.post("/admin/inject/{kind}")
def inject_message(kind: str, db: Session = Depends(get_db)):
    """
    Experimentos de la Fase 10:
      duplicate      -> reenvía el último evento ya procesado (debe ignorarse)
      invalid_json   -> mensaje corrupto (debe ir a la DLQ sin reintentos)
      missing_fields -> evento sin sku (debe ir a la DLQ sin reintentos)
    """
    if kind == "duplicate":
        last = db.query(EventLog).order_by(EventLog.received_at.desc()).first()
        if not last:
            raise HTTPException(409, "Aún no hay eventos procesados para duplicar")
        body, key = json.dumps(last.payload), f"inventory.updated.{last.warehouse_id}"
    elif kind == "invalid_json":
        body, key = "{esto no es json", "inventory.updated.TEST"
    elif kind == "missing_fields":
        body, key = json.dumps({"event_id": "EVT-INVALIDO", "event_type": "INVENTORY_UPDATED", "payload": {}}), "inventory.updated.TEST"
    else:
        raise HTTPException(404, "kind debe ser duplicate, invalid_json o missing_fields")
    conn, ch = _channel()
    try:
        ch.basic_publish(messaging.EVENTS_EXCHANGE, key, body.encode(), messaging.persistent())
    finally:
        conn.close()
    return {"injected": kind}


# ==============================================================================
# Dashboard web (compatibilidad con index.html)
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open(INDEX_HTML_PATH, encoding="utf-8") as f:
        return f.read()


@app.get("/reports/events-by-warehouse")
def events_by_warehouse(db: Session = Depends(get_db)):
    summary = {wh: {"total_events": 0, "by_type": {}, "last_event_at": None} for wh in warehouses.warehouse_urls()}
    for wh, mtype, count, last in (db.query(EventLog.warehouse_id, EventLog.movement_type, func.count(), func.max(EventLog.received_at))
                                   .group_by(EventLog.warehouse_id, EventLog.movement_type).all()):
        s = summary.setdefault(wh, {"total_events": 0, "by_type": {}, "last_event_at": None})
        s["total_events"] += count
        s["by_type"][mtype] = count
        last = aware(last).isoformat()
        s["last_event_at"] = max(filter(None, [s["last_event_at"], last]))
    return {"generated_at": now().isoformat(),
            "total_events_received": sum(s["total_events"] for s in summary.values()),
            "warehouses_summary": summary}


@app.get("/reports/events")
def recent_events(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(EventLog).order_by(EventLog.received_at.desc()).limit(limit).all()
    return {
        "total_records": db.query(func.count(EventLog.event_id)).scalar(),
        "events": [{"event_id": e.event_id, "warehouse_id": e.warehouse_id, "event_type": e.movement_type,
                    "product_id": e.sku, "quantity": e.movement_quantity, "reference": e.reference,
                    "correlation_id": e.correlation_id, "received_at": aware(e.received_at).isoformat()} for e in rows],
    }


@app.post("/reports/reset")
def reset_feed(db: Session = Depends(get_db)):
    """Vacía el feed del dashboard. No toca el read model ni la tabla de idempotencia."""
    db.query(EventLog).delete()
    db.commit()
    return {"status": "ok"}


@app.post("/api/simulate-movement")
def simulate_movement(payload: Dict[str, Any]):
    """Formulario del dashboard: crea el producto (sku P-<id>) si no existe y registra el movimiento."""
    wh = payload.get("warehouse_id", "WH-001").upper()
    pid = int(payload.get("product_id", 101))
    sku = f"P-{pid:03d}"
    try:
        try:
            _, product = warehouses.request(wh, "GET", f"/products/by-sku/{sku}")
        except warehouses.WarehouseError as e:
            if e.status != 404:
                raise
            _, product = warehouses.request(wh, "POST", "/products", {
                "sku": sku, "name": payload.get("product_name") or f"Producto {pid}", "unit": "UNIDAD", "category": "General"})
        _, result = warehouses.request(wh, "POST", "/inventory/movements", {
            "product_id": product["id"], "type": payload.get("movement_type", "RECEIPT").upper(),
            "quantity": int(payload.get("quantity", 10)), "reference": payload.get("reference")})
        return {"status": "success", "data": result}
    except warehouses.WarehouseError as e:
        return {"status": "error", "message": f"Error en bodega {wh}: {e.body}"}
    except Exception as e:
        return {"status": "error", "message": f"No se pudo conectar con {wh} ({e})"}


@app.get("/api/warehouse-audit/{warehouse_id}")
def warehouse_audit(warehouse_id: str):
    try:
        _, events = warehouses.request(warehouse_id, "GET", "/inventory/outbox/audit?limit=25", timeout=4)
        return {"status": "success", "warehouse_id": warehouse_id, "outbox_events": events}
    except Exception as e:
        return {"status": "error", "warehouse_id": warehouse_id, "outbox_events": [], "error": str(e)}
