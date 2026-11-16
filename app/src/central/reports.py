"""
Batch de reportes diarios -> S3 (Fase 8). Se ejecuta:
  - de forma asíncrona: POST /reports -> cola central.reports -> worker (202 + job_id);
  - de forma programada: python batch.py [--date AAAA-MM-DD] (cron diario en la EC2 central).
Es reejecutable: las claves en S3 dependen solo de la fecha, así que una reejecución
sobrescribe el resultado anterior, y cada ejecución queda registrada en report_jobs.
"""
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from consumers import PermanentError
from db import EventLog, InventoryView, ReportJob, now, session_scope
from shared.observability import log

logger = logging.getLogger("reports")
BUCKET = os.getenv("S3_BUCKET", "")
LOCAL_DIR = os.getenv("REPORTS_DIR", "/tmp/reports")
TERMINAL = {"COMPLETED", "FAILED"}


def put_json(key: str, data: dict) -> str:
    body = json.dumps(data, default=str, ensure_ascii=False, indent=2).encode()
    if BUCKET:
        import boto3  # credenciales: LabInstanceProfile vía metadata service
        boto3.client("s3").put_object(Bucket=BUCKET, Key=key, Body=body, ContentType="application/json")
        return f"s3://{BUCKET}/{key}"
    path = os.path.join(LOCAL_DIR, key)  # desarrollo local sin S3
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return f"file://{path}"


def build_daily_report(day: date, job_id: str):
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    with session_scope() as db:
        events = db.query(EventLog).filter(EventLog.occurred_at >= start, EventLog.occurred_at < start + timedelta(days=1)).all()
        snapshot = db.query(InventoryView).all()
        per_wh = defaultdict(lambda: {"movements": 0, "by_type": defaultdict(int), "units_by_type": defaultdict(int), "skus": set()})
        for e in events:
            w = per_wh[e.warehouse_id]
            w["movements"] += 1
            w["by_type"][e.movement_type] += 1
            w["units_by_type"][e.movement_type] += e.movement_quantity
            w["skus"].add(e.sku)
        inventory = defaultdict(list)
        for r in snapshot:
            inventory[r.warehouse_id].append({"sku": r.sku, "name": r.product_name, "quantity": r.quantity,
                                              "reserved_quantity": r.reserved_quantity, "version": r.version})
    report = {
        "report_type": "daily_movements",
        "schema_version": 1,
        "date": day.isoformat(),
        "job_id": job_id,
        "generated_at": now().isoformat(),
        "totals": {"warehouses": len(per_wh), "movements": len(events)},
        "warehouses": {wh: {"movements": w["movements"], "by_type": dict(w["by_type"]),
                            "units_by_type": dict(w["units_by_type"]), "distinct_skus": len(w["skus"])}
                       for wh, w in sorted(per_wh.items())},
    }
    return report, inventory


def run_job(job_id: str):
    with session_scope() as db:
        job = db.get(ReportJob, job_id)
        if job is None:
            raise PermanentError(f"job inexistente: {job_id}")
        if job.status in TERMINAL:
            log(logger, "duplicate_job_ignored", job_id=job_id, status=job.status)
            return
        day = date.fromisoformat(job.report_date)
    report, inventory = build_daily_report(day, job_id)
    prefix = f"{day:%Y/%m}"
    locations = {"report": put_json(f"reports/daily/{prefix}/{day:%d}/report-{day}.json", report)}
    for wh, rows in inventory.items():
        locations[wh] = put_json(f"warehouses/{wh}/{prefix}/inventory-{day}.json",
                                 {"warehouse_id": wh, "date": day.isoformat(), "job_id": job_id, "inventory": rows})
    with session_scope() as db:
        job = db.get(ReportJob, job_id)
        job.status, job.finished_at = "COMPLETED", now()
        job.result = {"locations": locations, "totals": report["totals"]}
    log(logger, "report_completed", job_id=job_id, date=str(day), movements=report["totals"]["movements"])


def create_job(report_date: str, trigger: str) -> str:
    date.fromisoformat(report_date)  # valida el formato
    job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
    with session_scope() as db:
        db.add(ReportJob(id=job_id, type="daily", report_date=report_date, trigger=trigger, status="PROCESSING"))
    return job_id


def handle_report(msg: dict):
    run_job(msg.get("job_id"))


def on_report_dead(msg: dict, error: str):
    with session_scope() as db:
        job = db.get(ReportJob, msg.get("job_id"))
        if job and job.status not in TERMINAL:
            job.status, job.error, job.finished_at = "FAILED", error, now()
