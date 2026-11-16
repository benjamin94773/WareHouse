#!/usr/bin/env bash
# Escalones de carga sobre una bodega y resumen en tests/load/results/<label>.csv
#   tests/load/run.sh <BASE_URL> <label> [VUS...]
#   tests/load/run.sh http://1.2.3.4/api redis-on 100 500 1000
# Variables: DURATION (30s), WRITE_RATIO (0), PRODUCT_ID (1)
set -euo pipefail
cd "$(dirname "$0")"
BASE=${1:?BASE_URL}; LABEL=${2:?label}; shift 2
STEPS=("${@:-100}")
mkdir -p results
CSV="results/$LABEL.csv"
echo "label,vus,requests,rps,p50_ms,p95_ms,p99_ms,error_rate,cache_hit_rate" > "$CSV"
for VUS in "${STEPS[@]}"; do
  echo "== $LABEL: $VUS usuarios =="
  curl -s "$BASE/metrics" > "results/$LABEL-$VUS-metrics-antes.json" || true
  k6 run --quiet -e BASE_URL="$BASE" -e VUS="$VUS" -e LABEL="$LABEL" -e OUT="results/$LABEL-$VUS.json" inventory.js | grep RESULTADO || true
  curl -s "$BASE/metrics" > "results/$LABEL-$VUS-metrics-despues.json" || true
  python3 -c "import json,sys; r=json.load(open(sys.argv[1])); print(','.join(str(r[k]) for k in ['label','vus','requests','rps','p50_ms','p95_ms','p99_ms','error_rate','cache_hit_rate']))" \
    "results/$LABEL-$VUS.json" >> "$CSV"
  sleep 5  # deja drenar conexiones entre escalones
done
column -s, -t "$CSV"
