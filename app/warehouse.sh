#!/usr/bin/env bash
# Entorno local completo (central + 3 bodegas) en una sola máquina con Docker.
# Las bodegas publican su LB en 8001-8003 y se conectan a RabbitMQ vía host.docker.internal.
#   ./warehouse.sh up            levanta todo (API_REPLICAS=1 por defecto en local)
#   ./warehouse.sh down [-v]     baja todo (-v borra los datos)
#   ./warehouse.sh stop wh-002   detiene una bodega (prueba de fallo parcial)
set -euo pipefail
cd "$(dirname "$0")"
WAREHOUSES=(1 2 3)

wh() {  # wh <n> <args de docker compose...>
  local n=$1; shift
  WH_ID="WH-00$n" LB_PORT="800$n" API_REPLICAS="${API_REPLICAS:-1}" \
    docker compose -f docker-compose.warehouse.yml -p "wh00$n" "$@"
}

case "${1:-}" in
  up)
    docker compose -f docker-compose.central.yml up -d --build
    for n in "${WAREHOUSES[@]}"; do wh "$n" up -d --build; done
    echo "Central: http://localhost:8080 | RabbitMQ: http://localhost:15672 | Bodegas: http://localhost:8001-8003"
    ;;
  down)
    for n in "${WAREHOUSES[@]}"; do wh "$n" down "${@:2}"; done
    docker compose -f docker-compose.central.yml down "${@:2}"
    ;;
  stop|start)
    n="${2:?indica la bodega, p. ej. wh-002}"; wh "${n: -1}" "$1"
    ;;
  ps)
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    ;;
  *)
    sed -n '2,7p' "$0"; exit 1
    ;;
esac
