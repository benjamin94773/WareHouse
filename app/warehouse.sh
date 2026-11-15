#!/usr/bin/env bash

# ==============================================================================
# Script de Gestión de Bodegas Autónomas — Warehouse Cloud Platform
# ==============================================================================
# Permite levantar, detener, reiniciar y crear bodegas de forma aislada
# utilizando la plantilla parametrizada docker/composes/compose-warehouse.yml.
# ==============================================================================

set -e

# Asegurar que siempre corremos desde la raíz de warehouse_cloud_project
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_TEMPLATE="docker/composes/compose-warehouse.yml"

# Colores para la terminal
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
RESET="\033[0m"

mostrar_ayuda() {
    echo -e "${BOLD}Uso:${RESET} ./warehouse.sh <comando> <bodega> [opciones]"
    echo ""
    echo -e "${BOLD}Comandos disponibles:${RESET}"
    echo -e "  ${GREEN}up${RESET} <bodega> [--build]       Levanta una bodega específica en segundo plano"
    echo -e "  ${RED}down${RESET} <bodega> [-v]            Baja y destruye los contenedores de una bodega"
    echo -e "  ${YELLOW}restart${RESET} <bodega>             Reinicia los servicios de una bodega"
    echo -e "  ${BLUE}status | ps${RESET} [bodega]         Muestra el estado de los contenedores"
    echo -e "  ${BLUE}logs${RESET} <bodega>                 Muestra los logs en vivo de una bodega"
    echo -e "  ${GREEN}create${RESET} <bodega> [db] [api] [fe]  Crea una nueva bodega copiando plantilla y puertos"
    echo ""
    echo -e "${BOLD}Ejemplos:${RESET}"
    echo "  ./warehouse.sh up wh-001"
    echo "  ./warehouse.sh up wh_002 --build"
    echo "  ./warehouse.sh down wh-001"
    echo "  ./warehouse.sh down wh-002 -v        (elimina también los volúmenes de datos)"
    echo "  ./warehouse.sh create wh-003 5435 8003 8083"
    echo "  ./warehouse.sh up all"
    echo "  ./warehouse.sh down all"
    exit 1
}

# Normalizar nombre y encontrar el archivo .env
resolver_env() {
    local target="$1"
    local env_path=""

    if [ -f "docker/components/${target}/.env" ]; then
        env_path="docker/components/${target}/.env"
    elif [ -f "docker/components/${target//-/_}/.env" ]; then
        env_path="docker/components/${target//-/_}/.env"
    elif [ -f "docker/components/${target//_/-}/.env" ]; then
        env_path="docker/components/${target//_/-}/.env"
    fi

    if [ -z "$env_path" ]; then
        echo -e "${RED}[ERROR] No se encontró configuración .env para la bodega '${target}'.${RESET}"
        echo -e "Asegúrate de que exista la carpeta en docker/components/${target}/.env"
        exit 1
    fi

    echo "$env_path"
}

# Listar todas las bodegas configuradas
listar_bodegas() {
    find docker/components -mindepth 1 -maxdepth 1 -type d -name "wh_*" -exec basename {} \; | sort
}

# Comando principal
ACCION="$1"
BODEGA="$2"
shift 2 2>/dev/null || true
OPCIONES="$@"

if [ -z "$ACCION" ]; then
    mostrar_ayuda
fi

case "$ACCION" in
    up)
        if [ "$BODEGA" = "all" ]; then
            for wh in $(listar_bodegas); do
                "$0" up "$wh" $OPCIONES
            done
            exit 0
        fi

        if [ -z "$BODEGA" ]; then
            echo -e "${RED}[ERROR] Debes especificar la bodega a levantar (ej: wh-001, wh-002 o all).${RESET}"
            exit 1
        fi

        ENV_FILE=$(resolver_env "$BODEGA")
        PROJECT_NAME="${BODEGA//-/_}"

        echo -e "${GREEN}[+] Levantando bodega ${BOLD}${PROJECT_NAME}${RESET} con ${ENV_FILE}...${RESET}"
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_TEMPLATE" -p "$PROJECT_NAME" up -d $OPCIONES
        echo -e "${GREEN}[✓] Bodega ${PROJECT_NAME} en ejecución.${RESET}"
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_TEMPLATE" -p "$PROJECT_NAME" ps
        ;;

    down)
        if [ "$BODEGA" = "all" ]; then
            for wh in $(listar_bodegas); do
                "$0" down "$wh" $OPCIONES
            done
            exit 0
        fi

        if [ -z "$BODEGA" ]; then
            echo -e "${RED}[ERROR] Debes especificar la bodega a bajar (ej: wh-001, wh-002 o all).${RESET}"
            exit 1
        fi

        ENV_FILE=$(resolver_env "$BODEGA")
        PROJECT_NAME="${BODEGA//-/_}"

        echo -e "${YELLOW}[-] Deteniendo bodega ${BOLD}${PROJECT_NAME}${RESET}...${RESET}"
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_TEMPLATE" -p "$PROJECT_NAME" down $OPCIONES
        echo -e "${YELLOW}[✓] Bodega ${PROJECT_NAME} detenida.${RESET}"
        ;;

    restart)
        "$0" down "$BODEGA"
        "$0" up "$BODEGA" $OPCIONES
        ;;

    status|ps)
        if [ -z "$BODEGA" ] || [ "$BODEGA" = "all" ]; then
            docker ps --filter "name=warehouse" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        else
            ENV_FILE=$(resolver_env "$BODEGA")
            PROJECT_NAME="${BODEGA//-/_}"
            docker compose --env-file "$ENV_FILE" -f "$COMPOSE_TEMPLATE" -p "$PROJECT_NAME" ps
        fi
        ;;

    logs)
        if [ -z "$BODEGA" ]; then
            echo -e "${RED}[ERROR] Debes especificar la bodega para ver logs.${RESET}"
            exit 1
        fi
        ENV_FILE=$(resolver_env "$BODEGA")
        PROJECT_NAME="${BODEGA//-/_}"
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_TEMPLATE" -p "$PROJECT_NAME" logs -f $OPCIONES
        ;;

    create)
        NUEVA_BODEGA="$BODEGA"
        if [ -z "$NUEVA_BODEGA" ]; then
            echo -e "${RED}[ERROR] Debes indicar el nombre de la nueva bodega (ej: wh-003).${RESET}"
            exit 1
        fi

        DIR_NAME="${NUEVA_BODEGA//-/_}"
        TARGET_DIR="docker/components/${DIR_NAME}"

        if [ -d "$TARGET_DIR" ]; then
            echo -e "${RED}[ERROR] La bodega ${DIR_NAME} ya existe en ${TARGET_DIR}.${RESET}"
            exit 1
        fi

        # Obtener puertos por parámetros o calcularlos automáticamente
        DB_PORT="${1:-5435}"
        BE_PORT="${2:-8003}"
        FE_PORT="${3:-8083}"

        WH_ID_UPPER=$(echo "$DIR_NAME" | tr '[:lower:]' '[:upper:]' | tr '_' '-')

        mkdir -p "$TARGET_DIR"
        cat <<EOF > "${TARGET_DIR}/.env"
WH_ID=${WH_ID_UPPER}
DB_PORT=${DB_PORT}
BE_PORT=${BE_PORT}
FE_PORT=${FE_PORT}
EOF

        # Crear symlink con guiones si se usó guión bajo
        cd docker/components
        ln -sf "${DIR_NAME}" "${DIR_NAME//_/-}"
        cd "$PROJECT_ROOT"

        echo -e "${GREEN}[✓] Nueva bodega creada exitosamente en ${TARGET_DIR}:${RESET}"
        cat "${TARGET_DIR}/.env"
        echo ""
        echo -e "Puedes levantarla con:"
        echo -e "  ${BOLD}./warehouse.sh up ${NUEVA_BODEGA}${RESET}"
        ;;

    *)
        mostrar_ayuda
        ;;
esac
