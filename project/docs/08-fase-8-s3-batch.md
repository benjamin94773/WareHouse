# Fase 8 — S3 y Batch

## Objetivo

Separar almacenamiento histórico y procesamiento masivo de las operaciones transaccionales.

## S3

Estructura sugerida:

```text
warehouse-platform/
  warehouses/
    WH-001/
      2026/
        09/
          inventory-2026-09-28.json
  reports/
  audit/
  exports/
```

## Batch

Ejemplo:

```text
23:00
  |
  v
Leer movimientos
  |
  v
Procesar todas las bodegas
  |
  v
Generar reporte
  |
  v
Guardar en S3
```

## Requisitos

El proceso Batch debe:

- procesar datos de varias bodegas;
- generar un reporte;
- almacenarlo en S3;
- registrar su ejecución;
- ser reejecutable.

## Preguntas

- ¿Por qué no generar este reporte dentro del request HTTP?
- ¿Cuándo usar Batch?
- ¿Cuándo usar un worker?
- ¿Cuándo usar Lambda?
