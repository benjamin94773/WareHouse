#!/usr/bin/env bash
# Despliega el código local en las EC2 creadas por Terraform (sin pasar por GitHub).
#   scripts/deploy.sh               central y luego las 3 bodegas en paralelo
#   scripts/deploy.sh wh-002        solo una máquina
# Variables opcionales: API_REPLICAS (3), CACHE_ENABLED (true).
set -euo pipefail
cd "$(dirname "$0")/.."

KEY=labsuser.pem
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10)

# Secretos generados una sola vez y fuera de git (.deploy.env está en .gitignore)
if [ ! -f .deploy.env ]; then
  {
    echo "RABBITMQ_USER=warehouse"
    echo "RABBITMQ_PASS=$(openssl rand -hex 16)"
    echo "DB_PASSWORD=$(openssl rand -hex 16)"
    echo "CENTRAL_DB_PASSWORD=$(openssl rand -hex 16)"
  } > .deploy.env
  chmod 600 .deploy.env
fi

TF=$(terraform output -json)
tf() { python3 -c "import json,sys; o=json.loads(sys.argv[1]); print(eval(sys.argv[2]))" "$TF" "$1"; }
CENTRAL_PUBLIC=$(tf "o['central']['value']['public_ip']")
CENTRAL_PRIVATE=$(tf "o['central']['value']['private_ip']")
BUCKET=$(tf "o['s3_bucket']['value']")
WAREHOUSE_URLS=$(tf "','.join(f\"{k.upper()}=http://{v['private_ip']}/api\" for k, v in sorted(o['bodegas_ips']['value'].items()))")

deploy() {  # deploy <nombre> <ip pública> <compose> <contenido extra del .env>
  local name=$1 ip=$2 compose=$3 env=$4
  echo "[$name] esperando a que termine el user data en $ip..."
  until ssh "${SSH_OPTS[@]}" "ubuntu@$ip" "cloud-init status --wait >/dev/null; command -v docker" >/dev/null 2>&1; do sleep 10; done
  rsync -az --delete -e "ssh ${SSH_OPTS[*]}" --exclude '__pycache__' --exclude '*.db' --exclude '.pytest_cache' --exclude '.env' \
    app/ "ubuntu@$ip:app/"
  { cat .deploy.env; echo "$env"; } | ssh "${SSH_OPTS[@]}" "ubuntu@$ip" "cat > app/.env && chmod 600 app/.env"
  ssh "${SSH_OPTS[@]}" "ubuntu@$ip" "cd app && sudo docker compose -f $compose up -d --build --remove-orphans" 2>&1 | sed "s/^/[$name] /"
  echo "[$name] listo"
}

deploy_warehouse() {
  local name=$1
  local ip; ip=$(tf "o['bodegas_ips']['value']['$name']['public_ip']")
  deploy "$name" "$ip" docker-compose.warehouse.yml "$(printf 'WH_ID=%s\nRABBITMQ_HOST=%s\nAPI_REPLICAS=%s\nCACHE_ENABLED=%s\nCOMPOSE_PROJECT_NAME=warehouse' \
    "$(echo "$name" | tr a-z A-Z)" "$CENTRAL_PRIVATE" "${API_REPLICAS:-3}" "${CACHE_ENABLED:-true}")"
}

TARGET=${1:-all}
if [[ $TARGET == all || $TARGET == central ]]; then
  # La central va primero: declara las colas a las que publican las bodegas
  deploy central "$CENTRAL_PUBLIC" docker-compose.central.yml "$(printf 'WAREHOUSES=%s\nS3_BUCKET=%s' "$WAREHOUSE_URLS" "$BUCKET")"
  # Batch diario a las 23:00 UTC (reporte + snapshots en S3); log en ~/batch.log
  ssh "${SSH_OPTS[@]}" "ubuntu@$CENTRAL_PUBLIC" "(crontab -l 2>/dev/null | grep -v batch.py; \
    echo '0 23 * * * cd /home/ubuntu/app && docker compose -f docker-compose.central.yml exec -T central_worker python batch.py >> /home/ubuntu/batch.log 2>&1') | crontab -"
fi
if [[ $TARGET == all ]]; then
  for wh in $(tf "' '.join(sorted(o['bodegas_ips']['value']))"); do deploy_warehouse "$wh" & done
  wait
elif [[ $TARGET != central ]]; then
  deploy_warehouse "$TARGET"
fi

echo
echo "Central:  http://$CENTRAL_PUBLIC:8080   (docs: /docs, RabbitMQ: http://$CENTRAL_PUBLIC:15672)"
tf "'\n'.join(f\"{k}:   http://{v['public_ip']}   (API: /api/docs)\" for k, v in sorted(o['bodegas_ips']['value'].items()))"
