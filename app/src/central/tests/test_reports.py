import json

import reports
from consumers import project_inventory_event
from db import ReportJob, SessionLocal
from tests.conftest import event


def test_batch_diario_genera_reporte_y_snapshots_reejecutable(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "LOCAL_DIR", str(tmp_path))
    project_inventory_event(event("E1", wh="WH-001", qty=10, mtype="RECEIPT"))
    project_inventory_event(event("E2", wh="WH-002", qty=5, mtype="RECEIPT"))

    for _ in range(2):  # reejecutable: misma salida, dos ejecuciones registradas
        job = reports.create_job("2026-11-15", trigger="cli")
        reports.run_job(job)

    report = json.loads((tmp_path / "reports/daily/2026/11/15/report-2026-11-15.json").read_text())
    assert report["totals"] == {"warehouses": 2, "movements": 2}
    assert report["warehouses"]["WH-001"]["units_by_type"] == {"RECEIPT": 10}
    assert (tmp_path / "warehouses/WH-002/2026/11/inventory-2026-11-15.json").exists()
    with SessionLocal() as db:
        assert [j.status for j in db.query(ReportJob)] == ["COMPLETED", "COMPLETED"]


def test_job_duplicado_se_ignora(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "LOCAL_DIR", str(tmp_path))
    job = reports.create_job("2026-11-15", trigger="api")
    reports.run_job(job)
    reports.run_job(job)  # mensaje duplicado
    with SessionLocal() as db:
        assert db.get(ReportJob, job).status == "COMPLETED"
