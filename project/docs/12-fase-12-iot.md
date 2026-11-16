# Fase 12 — Extensión IoT

## Objetivo

Integrar sensores físicos o simulados en cada bodega.

## Arquitectura

```text
Sensor
  |
  v
MQTT
  |
  v
Gateway / Edge
  |
  v
Ingestion Service
  |
  v
RabbitMQ
  |
  +--> Storage
  +--> Alerts
  +--> Analytics
```

## Sensores

- temperatura;
- humedad;
- movimiento;
- apertura;
- energía.

## Evento

```json
{
  "event_id": "EVT-100",
  "sequence_number": 150,
  "warehouse_id": "WH-001",
  "sensor_id": "TEMP-001",
  "value": 8.4,
  "timestamp": "2026-09-28T15:00:00Z"
}
```

## Problemas a estudiar

- mensajes duplicados;
- mensajes fuera de orden;
- pérdida de conexión;
- buffering;
- sequence numbers;
- idempotencia;
- consistencia eventual.

## Actividad

Simular:

```text
100 sensores
```

en:

```text
5 bodegas
```

Generar eventos periódicamente y analizar:

- throughput;
- latencia;
- pérdida de mensajes;
- duplicados;
- comportamiento ante caída de red.
