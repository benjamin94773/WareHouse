"""
Lambda: S3 Object Created vía EventBridge (reports/*.json) -> validar -> transformar -> registrar -> publicar evento.

- validar: estructura y coherencia de los totales del reporte diario;
- transformar: resumen compacto (movimientos y unidades por bodega);
- registrar: metadata/<clave>.meta.json en el mismo bucket (fuera de reports/ para no
  volver a disparar la función);
- publicar: POST a la central (/integrations/lambda-events). Si la central no responde
  se registra en CloudWatch y no se reintenta: la metadata en S3 ya es la fuente de verdad.
"""
import json
import os
import urllib.parse
import urllib.request

REQUIRED = ("report_type", "date", "job_id", "totals", "warehouses")


def validate(report) -> list:
    if not isinstance(report, dict):
        return ["el reporte no es un objeto JSON"]
    errors = [f"falta el campo {f}" for f in REQUIRED if f not in report]
    if errors:
        return errors
    whs = report["warehouses"]
    if report["totals"].get("warehouses") != len(whs):
        errors.append("totals.warehouses no coincide con el detalle")
    if report["totals"].get("movements") != sum(w.get("movements", 0) for w in whs.values()):
        errors.append("totals.movements no coincide con la suma por bodega")
    return errors


def summarize(report) -> dict:
    return {wh: {"movements": w.get("movements", 0), "units": sum(w.get("units_by_type", {}).values())}
            for wh, w in report.get("warehouses", {}).items()}


def publish(event: dict):
    url = os.environ.get("CENTRAL_URL")
    if not url:
        return "sin CENTRAL_URL"
    req = urllib.request.Request(f"{url}/integrations/lambda-events", data=json.dumps(event).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except Exception as e:
        print(json.dumps({"level": "WARNING", "event": "central_unreachable", "error": str(e)}))
        return str(e)


def objects(event):
    """Acepta el evento de EventBridge (Object Created) y el formato clásico de notificación S3."""
    if "detail" in event:
        yield event["detail"]["bucket"]["name"], event["detail"]["object"]["key"]
    for record in event.get("Records", []):
        yield record["s3"]["bucket"]["name"], urllib.parse.unquote_plus(record["s3"]["object"]["key"])


def lambda_handler(event, context):
    import boto3  # incluido en el runtime de Lambda
    s3 = boto3.client("s3")
    results = []
    for bucket, key in objects(event):
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        try:
            report = json.loads(body)
            errors = validate(report)
        except ValueError as e:
            report, errors = {}, [f"JSON inválido: {e}"]
        meta = {
            "key": key,
            "size_bytes": len(body),
            "valid": not errors,
            "errors": errors,
            "report_date": report.get("date"),
            "job_id": report.get("job_id"),
            "summary": summarize(report) if not errors else None,
            "request_id": getattr(context, "aws_request_id", None),
        }
        s3.put_object(Bucket=bucket, Key=f"metadata/{key}.meta.json", Body=json.dumps(meta, ensure_ascii=False).encode(),
                      ContentType="application/json")
        meta["central_response"] = publish(meta)
        print(json.dumps({"level": "INFO" if not errors else "ERROR", "event": "report_validated", **meta}, ensure_ascii=False))
        results.append(meta)
    return {"processed": len(results), "results": results}
