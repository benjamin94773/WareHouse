#!/usr/bin/env python3
"""
Simulador de sensores IoT para bodegas (Fase 12 — Extensión IoT).
Genera telemetría (temperatura, humedad, movimiento, energía) para múltiples sensores,
simulando desafíos distribuidos: mensajes duplicados, fuera de orden y buffering por desconexión.
Soporta publicación directa al Servicio de Ingestión de la Central (HTTP) o RabbitMQ.

Uso:
    python scripts/simulate_iot.py --sensors 20 --duration 10
    python scripts/simulate_iot.py --benchmark-100-5
    python scripts/simulate_iot.py --publish http://localhost:8080/api/iot/telemetry --sensors 10
"""
import argparse
import json
import random
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

SENSOR_TYPES = {
    "TEMP": {"unit": "C", "min": 2.0, "max": 18.0},
    "HUM": {"unit": "%", "min": 30.0, "max": 75.0},
    "MOV": {"unit": "bool", "min": 0, "max": 1},
    "PWR": {"unit": "kWh", "min": 0.5, "max": 12.0},
}


def generate_event(warehouse_id: str, sensor_id: str, sensor_type: str, seq_num: int) -> dict:
    cfg = SENSOR_TYPES[sensor_type]
    val = round(random.uniform(cfg["min"], cfg["max"]), 2) if cfg["unit"] != "bool" else random.choice([0, 1])
    return {
        "event_id": f"EVT-IOT-{uuid.uuid4().hex[:8].upper()}",
        "sequence_number": seq_num,
        "warehouse_id": warehouse_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "value": val,
        "unit": cfg["unit"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_to_api(target_url: str, payload: dict) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(target_url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status in (200, 201, 202)
    except Exception:
        return False


def run_simulation(
    warehouses: list,
    sensor_count: int,
    duration_s: int,
    interval_s: float,
    duplicate_prob: float,
    out_of_order_prob: float,
    simulate_disconnect: bool = False,
    output_file: str = None,
    publish_url: str = None,
):
    print("=" * 70)
    print("Iniciando simulación de sensores IoT (Fase 12 — Extensión IoT)")
    print(f"Bodegas ({len(warehouses)}): {', '.join(warehouses)}")
    print(f"Sensores totales: {sensor_count} | Duración: {duration_s}s | Intervalo: {interval_s}s")
    print(f"Probabilidad duplicados: {duplicate_prob:.1%} | Fuera de orden: {out_of_order_prob:.1%}")
    if publish_url:
        print(f"Modo publicación: Ingestion Service ({publish_url})")
    if simulate_disconnect:
        print("Modo resiliencia: Simulación de pérdida temporal de red y buffering local activa")
    print("=" * 70)

    sensors = []
    types = list(SENSOR_TYPES.keys())
    for i in range(sensor_count):
        stype = types[i % len(types)]
        wh = warehouses[i % len(warehouses)]
        sensors.append({
            "id": f"{stype}-{i+1:03d}",
            "type": stype,
            "warehouse": wh,
            "seq": 0,
        })

    start_time = time.time()
    events_generated = 0
    duplicates_injected = 0
    buffer = []
    published_ok = 0
    published_failed = 0
    out_file = open(output_file, "w", encoding="utf-8") if output_file else None

    # Simular ventana de desconexión en la mitad
    disconnect_window_start = duration_s * 0.3 if simulate_disconnect else -1
    disconnect_window_end = duration_s * 0.6 if simulate_disconnect else -1

    try:
        while time.time() - start_time < duration_s:
            elapsed = time.time() - start_time
            is_disconnected = disconnect_window_start <= elapsed <= disconnect_window_end

            for s in sensors:
                s["seq"] += 1
                evt = generate_event(s["warehouse"], s["id"], s["type"], s["seq"])
                buffer.append(evt)
                events_generated += 1

                # Inyección intencional de duplicados
                if duplicate_prob > 0 and random.random() < duplicate_prob:
                    buffer.append(evt)
                    duplicates_injected += 1

            # Simulación de entrega fuera de orden
            if out_of_order_prob > 0 and len(buffer) > 1 and random.random() < out_of_order_prob:
                random.shuffle(buffer)

            # Si hay desconexión temporal, los eventos se acumulan en buffer local (Edge Buffering)
            if is_disconnected:
                print(f"[EDGE BUFFERING] Red caída temporalmente. {len(buffer)} telemetrías retenidas en memoria...")
            else:
                # Flujo normal o descarga tras reconexión
                while buffer:
                    item = buffer.pop(0)
                    line = json.dumps(item)
                    if out_file:
                        out_file.write(line + "\n")

                    if publish_url:
                        success = send_to_api(publish_url, item)
                        if success:
                            published_ok += 1
                        else:
                            published_failed += 1
                    elif not out_file and events_generated <= 20:
                        print(f"[{item['warehouse_id']}] {item['sensor_id']} (#{item['sequence_number']}): {item['value']} {item['unit']} (ID: {item['event_id']})")

            time.sleep(interval_s)

        # Vaciar buffer residual al terminar si se reconectó
        while buffer:
            item = buffer.pop(0)
            if out_file:
                out_file.write(json.dumps(item) + "\n")
            if publish_url:
                if send_to_api(publish_url, item):
                    published_ok += 1
                else:
                    published_failed += 1

    except KeyboardInterrupt:
        print("\nSimulación interrumpida por el usuario.")
    finally:
        if out_file:
            out_file.close()

    elapsed = round(time.time() - start_time, 2)
    rps = round(events_generated / elapsed, 1) if elapsed > 0 else 0
    print("\n" + "=" * 70)
    print("Resultados de la simulación IoT:")
    print(f"Tiempo total: {elapsed} s")
    print(f"Eventos únicos generados: {events_generated}")
    print(f"Duplicados inyectados: {duplicates_injected}")
    print(f"Throughput de generación: {rps} eventos/segundo")
    if publish_url:
        print(f"Telemetrías publicadas con éxito: {published_ok}")
        print(f"Telemetrías fallidas (red/broker): {published_failed}")
    if output_file:
        print(f"Eventos guardados en archivo: {output_file}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Simulador de Sensores IoT para Bodegas")
    parser.add_argument("--warehouses", nargs="+", default=["WH-001", "WH-002", "WH-003"], help="IDs de bodegas")
    parser.add_argument("--sensors", type=int, default=12, help="Cantidad de sensores a simular")
    parser.add_argument("--duration", type=int, default=5, help="Duración en segundos")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervalo de telemetría por sensor")
    parser.add_argument("--duplicates", action="store_true", help="Inyectar duplicados (~10%)")
    parser.add_argument("--out-of-order", action="store_true", help="Simular desorden en entrega (~15%)")
    parser.add_argument("--simulate-disconnect", action="store_true", help="Simular pérdida y reconexión de red")
    parser.add_argument("--publish", type=str, default=None, help="URL del Ingestion Service (ej. http://localhost:8080/api/iot/telemetry)")
    parser.add_argument("--output", type=str, default=None, help="Archivo JSONL de salida opcional")
    parser.add_argument("--benchmark-100-5", action="store_true", help="Ejecutar prueba de 100 sensores en 5 bodegas")
    args = parser.parse_args()

    if args.benchmark_100_5:
        # Escenario estándar de la guía docente: 100 sensores en 5 bodegas
        run_simulation(
            warehouses=["WH-001", "WH-002", "WH-003", "WH-004", "WH-005"],
            sensor_count=100,
            duration_s=10,
            interval_s=1.0,
            duplicate_prob=0.10,
            out_of_order_prob=0.15,
            simulate_disconnect=True,
            output_file=args.output,
            publish_url=args.publish,
        )
    else:
        run_simulation(
            warehouses=args.warehouses,
            sensor_count=args.sensors,
            duration_s=args.duration,
            interval_s=args.interval,
            duplicate_prob=0.10 if args.duplicates else 0.0,
            out_of_order_prob=0.15 if args.out_of_order else 0.0,
            simulate_disconnect=args.simulate_disconnect,
            output_file=args.output,
            publish_url=args.publish,
        )


if __name__ == "__main__":
    main()
