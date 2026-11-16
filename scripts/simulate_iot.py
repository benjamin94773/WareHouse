#!/usr/bin/env python3
"""
Simulador de sensores IoT para bodegas (Fase 12 — Extensión IoT).
Genera telemetría (temperatura, humedad, movimiento, energía) para múltiples sensores,
simulando desafíos distribuidos: mensajes duplicados, fuera de orden y buffering por desconexión.

Uso:
    python scripts/simulate_iot.py --sensors 20 --duration 10
    python scripts/simulate_iot.py --warehouses WH-001 WH-002 WH-003 --duplicates --out-of-order
"""
import argparse
import json
import random
import time
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


def run_simulation(
    warehouses: list,
    sensor_count: int,
    duration_s: int,
    interval_s: float,
    duplicate_prob: float,
    out_of_order_prob: float,
    output_file: str = None,
):
    print("=" * 65)
    print("Iniciando simulación de sensores IoT (Fase 12 — Extensión IoT)")
    print(f"Bodegas: {', '.join(warehouses)}")
    print(f"Sensores totales: {sensor_count} | Duración: {duration_s}s | Intervalo: {interval_s}s")
    print(f"Probabilidad duplicados: {duplicate_prob:.1%} | Fuera de orden: {out_of_order_prob:.1%}")
    print("=" * 65)

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
    out_file = open(output_file, "w", encoding="utf-8") if output_file else None

    try:
        while time.time() - start_time < duration_s:
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

            # Envío / registro de eventos acumulados
            while buffer:
                item = buffer.pop(0)
                line = json.dumps(item)
                if out_file:
                    out_file.write(line + "\n")
                else:
                    print(f"[{item['warehouse_id']}] {item['sensor_id']} (#{item['sequence_number']}): {item['value']} {item['unit']} (ID: {item['event_id']})")

            time.sleep(interval_s)

    except KeyboardInterrupt:
        print("\nSimulación interrumpida por el usuario.")
    finally:
        if out_file:
            out_file.close()

    elapsed = round(time.time() - start_time, 2)
    rps = round(events_generated / elapsed, 1) if elapsed > 0 else 0
    print("\n" + "=" * 65)
    print("Resultados de la simulación IoT:")
    print(f"Tiempo total: {elapsed} s")
    print(f"Eventos únicos generados: {events_generated}")
    print(f"Duplicados inyectados: {duplicates_injected}")
    print(f"Throughput promedio: {rps} eventos/segundo")
    if output_file:
        print(f"Eventos guardados en: {output_file}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Simulador de Sensores IoT para Bodegas")
    parser.add_argument("--warehouses", nargs="+", default=["WH-001", "WH-002", "WH-003"], help="IDs de bodegas")
    parser.add_argument("--sensors", type=int, default=12, help="Cantidad de sensores a simular")
    parser.add_argument("--duration", type=int, default=5, help="Duración en segundos")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervalo de telemetría por sensor")
    parser.add_argument("--duplicates", action="store_true", help="Inyectar duplicados (~10%)")
    parser.add_argument("--out-of-order", action="store_true", help="Simular desorden en entrega (~15%)")
    parser.add_argument("--output", type=str, default=None, help="Archivo JSONL de salida opcional")
    args = parser.parse_args()

    run_simulation(
        warehouses=args.warehouses,
        sensor_count=args.sensors,
        duration_s=args.duration,
        interval_s=args.interval,
        duplicate_prob=0.10 if args.duplicates else 0.0,
        out_of_order_prob=0.15 if args.out_of_order else 0.0,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
