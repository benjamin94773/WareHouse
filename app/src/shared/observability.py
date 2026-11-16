"""
Observabilidad compartida por la API de bodega y la central:
- correlation_id por request (cabecera X-Correlation-ID) propagado a eventos y llamadas HTTP;
- logs JSON estructurados;
- métricas de la API en memoria (por instancia/réplica).
"""
import contextvars
import json
import logging
import os
import socket
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

SERVICE = os.getenv("SERVICE_NAME", "warehouse-api")
INSTANCE = socket.gethostname()  # con varias réplicas permite ver a cuál llegó cada request
CORRELATION_HEADER = "X-Correlation-ID"

correlation_id = contextvars.ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return f"COR-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": utc_now_iso(),
            "service": SERVICE,
            "instance": INSTANCE,
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        cid = correlation_id.get()
        if cid:
            entry["correlation_id"] = cid
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True  # reemplazado por el log http_request


def log(logger: logging.Logger, event: str, level=logging.INFO, **fields):
    """log(logger, "inventory_updated", product_id=1) -> línea JSON con esos campos."""
    logger.log(level, event, extra={"fields": fields})


class ApiMetrics:
    """Contadores y latencias de las últimas N requests (percentiles aproximados)."""

    def __init__(self, window=2000):
        self.lock = threading.Lock()
        self.started = time.time()
        self.requests = 0
        self.errors = 0
        self.latencies = deque(maxlen=window)

    def record(self, status_code: int, duration_ms: float):
        with self.lock:
            self.requests += 1
            if status_code >= 500:
                self.errors += 1
            self.latencies.append(duration_ms)

    def snapshot(self) -> dict:
        with self.lock:
            lat = sorted(self.latencies)
            uptime = max(time.time() - self.started, 1e-9)
            pct = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 2) if lat else None
            return {
                "instance": INSTANCE,
                "requests_total": self.requests,
                "errors_5xx_total": self.errors,
                "error_rate": round(self.errors / self.requests, 4) if self.requests else 0,
                "avg_rps_since_start": round(self.requests / uptime, 2),
                "latency_ms": {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "window": len(lat)},
            }


metrics = ApiMetrics()
_http_logger = logging.getLogger("http")


def install(app):
    """Middleware: correlation_id + log por request + métricas."""

    @app.middleware("http")
    async def observe(request, call_next):
        cid = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        token = correlation_id.set(cid)
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[CORRELATION_HEADER] = cid
            return response
        finally:
            duration = (time.perf_counter() - start) * 1000
            metrics.record(status_code, duration)
            if request.url.path not in ("/health", "/metrics"):  # evita ruido de health checks
                log(_http_logger, "http_request", method=request.method, path=request.url.path,
                    status=status_code, duration_ms=round(duration, 2))
            correlation_id.reset(token)
