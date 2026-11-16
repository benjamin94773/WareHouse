from handler import summarize, validate

OK = {"report_type": "daily_movements", "date": "2026-11-15", "job_id": "JOB-1",
      "totals": {"warehouses": 1, "movements": 2},
      "warehouses": {"WH-001": {"movements": 2, "units_by_type": {"RECEIPT": 10, "SHIPMENT": 3}}}}


def test_reporte_valido():
    assert validate(OK) == []
    assert summarize(OK) == {"WH-001": {"movements": 2, "units": 13}}


def test_reporte_inconsistente_o_incompleto():
    assert validate({**OK, "totals": {"warehouses": 1, "movements": 5}}) == ["totals.movements no coincide con la suma por bodega"]
    assert "falta el campo job_id" in validate({k: v for k, v in OK.items() if k != "job_id"})
    assert validate([]) == ["el reporte no es un objeto JSON"]


def test_formatos_de_evento():
    from handler import objects
    eb = {"detail": {"bucket": {"name": "b"}, "object": {"key": "reports/x.json"}}}
    s3 = {"Records": [{"s3": {"bucket": {"name": "b"}, "object": {"key": "reports/a+b.json"}}}]}
    assert list(objects(eb)) == [("b", "reports/x.json")]
    assert list(objects(s3)) == [("b", "reports/a b.json")]
